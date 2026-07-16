import copy
import re
import traceback
from typing import List

from pr_agent.algo.pr_processing import retry_with_fallback_models
from pr_agent.algo.utils import (ModelType, PRReviewHeader, convert_to_markdown_v2,
                                 load_yaml, show_relevant_configurations)
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider_with_context
from pr_agent.log import get_logger
from pr_agent.servers.help import HelpMessage
from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions
from pr_agent.tools.pr_reviewer import PRReviewer


class PRReviewAndImprove:
    """
    Combined command that runs both /review and /improve, deduplicates findings,
    and publishes a single unified comment.
    """

    def __init__(self, pr_url: str, is_answer: bool = False, is_auto: bool = False,
                 args: list = None,
                 ai_handler=None):
        self.pr_url = pr_url
        self.args = args
        self.is_answer = is_answer
        self.is_auto = is_auto

        self.git_provider = get_git_provider_with_context(pr_url)

    async def run(self):
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping review_and_improve")
                return None

            get_logger().info(f'Running review_and_improve for PR: {self.pr_url} ...')

            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing combined review and suggestions...", is_temporary=True)

            # ===== Phase 1: Run review =====
            get_logger().info('Phase 1/2: Running review...')
            review_tool = PRReviewer(self.pr_url, is_answer=self.is_answer, is_auto=self.is_auto,
                                     args=self.args)
            await retry_with_fallback_models(review_tool._prepare_prediction, model_type=ModelType.REGULAR)

            if not review_tool.prediction:
                get_logger().warning(f"Review returned no prediction for PR: {self.pr_url}")
                self.git_provider.remove_initial_comment()
                return None

            # Parse review output
            review_data = load_yaml(
                review_tool.prediction.strip(),
                keys_fix_yaml=[
                    "ticket_compliance_check", "estimated_effort_to_review_[1-5]:",
                    "security_concerns:", "key_issues_to_review:",
                    "relevant_file:", "relevant_line:", "suggestion:"
                ],
                first_key='review', last_key='security_concerns'
            )

            if 'review' not in review_data:
                get_logger().exception("Failed to parse review data", artifact={"data": review_data})
                self.git_provider.remove_initial_comment()
                return None

            # Move key_issues_to_review to the end of dict (same as PRReviewer._prepare_pr_review)
            if 'key_issues_to_review' in review_data['review']:
                key_issues_to_review = review_data['review'].pop('key_issues_to_review')
                review_data['review']['key_issues_to_review'] = key_issues_to_review

            # ===== Phase 2: Run improve with dedup context =====
            get_logger().info('Phase 2/2: Running code suggestions...')
            review_issues = review_data['review'].get('key_issues_to_review', [])
            dedup_context = self._build_dedup_context(review_issues)

            # Save and inject dedup context into improve extra_instructions
            original_extra = get_settings().pr_code_suggestions.get('extra_instructions', '') or ''
            if dedup_context:
                if original_extra.strip():
                    dedup_context = original_extra.strip() + '\n\n' + dedup_context
                get_settings().set('pr_code_suggestions.extra_instructions', dedup_context)

            try:
                improve_tool = PRCodeSuggestions(self.pr_url, args=self.args)
                suggestions_data = await retry_with_fallback_models(
                    improve_tool.prepare_prediction_main, model_type=ModelType.REGULAR
                )
            finally:
                # Restore original extra_instructions
                get_settings().set('pr_code_suggestions.extra_instructions', original_extra)

            suggestions = (suggestions_data or {}).get('code_suggestions', [])
            suggestions_filtered = self._deduplicate_suggestions(suggestions, review_issues)

            # ===== Phase 3: Format combined output =====
            combined_md = self._combine_outputs(
                review_data, review_tool,
                suggestions_filtered, improve_tool if suggestions_filtered else None
            )

            # ===== Phase 4: Publish =====
            if get_settings().config.publish_output:
                self.git_provider.remove_initial_comment()
                self.git_provider.publish_comment(combined_md)
                get_logger().info(f"Published combined review_and_improve for PR: {self.pr_url}")

            get_settings().data = {"artifact": combined_md}

        except Exception as e:
            get_logger().error(f"Failed to run review_and_improve for PR: {e}",
                               artifact={"traceback": traceback.format_exc()})
            if get_settings().config.publish_output:
                try:
                    self.git_provider.remove_initial_comment()
                    self.git_provider.publish_comment(
                        f"Failed to generate combined review and suggestions: {e}"
                    )
                except Exception:
                    pass

    def _build_dedup_context(self, review_issues: List[dict]) -> str:
        """
        Build a text snippet describing issues already flagged by the review,
        so the improve model can avoid suggesting improvements for the same code areas.
        """
        if not review_issues:
            return ""

        lines = [
            "The following issues have already been flagged in the PR review. "
            "DO NOT suggest improvements for code in these areas:"
        ]
        for issue in review_issues:
            if not isinstance(issue, dict):
                continue
            file = issue.get('relevant_file', '').strip()
            start = issue.get('start_line', '')
            end = issue.get('end_line', '')
            header = issue.get('issue_header', '').strip()
            if file:
                loc = f" lines {start}-{end}" if start and end else ""
                lines.append(f"- {file}{loc}: {header}")

        return "\n".join(lines)

    def _deduplicate_suggestions(self, suggestions: List[dict],
                                  review_issues: List[dict]) -> List[dict]:
        """
        Post-processing dedup: remove suggestions whose file+line range overlaps
        with a review issue.
        """
        if not suggestions or not review_issues:
            return suggestions

        def overlaps(suggestion, issue):
            if not isinstance(issue, dict) or not isinstance(suggestion, dict):
                return False
            if suggestion.get('relevant_file', '').strip() != issue.get('relevant_file', '').strip():
                return False
            s_start = suggestion.get('relevant_lines_start', 0) or 0
            s_end = suggestion.get('relevant_lines_end', 0) or 0
            i_start = issue.get('start_line', 0) or 0
            i_end = issue.get('end_line', 0) or 0
            # If either side lacks meaningful line info, don't deduplicate
            if not s_start or not s_end or not i_start or not i_end:
                return False
            return s_start <= i_end and s_end >= i_start

        filtered = []
        removed_count = 0
        for s in suggestions:
            if any(overlaps(s, issue) for issue in review_issues):
                removed_count += 1
                get_logger().debug(
                    f"Removed duplicate suggestion for {s.get('relevant_file')}: "
                    f"'{s.get('one_sentence_summary', '')}'"
                )
            else:
                filtered.append(s)

        if removed_count:
            get_logger().info(f"Removed {removed_count} duplicate suggestions overlapping with review issues")
        return filtered

    @staticmethod
    def _get_code_context(files, relevant_file: str, start_line: int, end_line: int) -> str:
        """Extract raw code lines from head_file for the given file and line range."""
        if not files or not relevant_file:
            return ""
        try:
            for f in files:
                if f.filename.strip() == relevant_file:
                    if not f.head_file:
                        return ""
                    lines = f.head_file.splitlines()
                    s = max(0, (start_line or 1) - 1)
                    e = min(len(lines), end_line or start_line or 1)
                    return "\n".join(lines[s:e])
        except Exception:
            pass
        return ""

    def _build_merged_suggestions(self, review_issues: List[dict],
                                   files, improve_suggestions: List[dict]) -> List[dict]:
        """
        Convert review issues to suggestion format with code context,
        then merge with improve suggestions into one sorted list.
        """
        merged = []
        for issue in review_issues:
            if not isinstance(issue, dict):
                continue

            header_lower = issue.get('issue_header', '').strip().lower()
            if 'security' in header_lower:
                label = 'security'
            elif 'bug' in header_lower:
                label = 'possible bug'
            else:
                label = 'possible issue'

            relevant_file = issue.get('relevant_file', '').strip()
            start_line = issue.get('start_line', 0) or 0
            end_line = issue.get('end_line', 0) or 0
            issue_content = issue.get('issue_content', '').strip()
            fix_suggestion = issue.get('suggestion_content', '').strip()

            # Get real code context from PR files
            existing_code = self._get_code_context(files, relevant_file, start_line, end_line)

            # suggestion_content is the fix suggestion (short) — not the full issue paragraph
            suggestion_content = fix_suggestion if fix_suggestion else issue_content

            pseudo = {
                'relevant_file': relevant_file,
                'relevant_lines_start': start_line,
                'relevant_lines_end': end_line,
                'one_sentence_summary': issue.get('issue_header', '').strip(),
                'suggestion_content': suggestion_content,
                'existing_code': existing_code,
                'improved_code': existing_code,  # same → diff shows context-only lines
                'label': label,
                'score': 9,
                'score_why': issue_content,
            }
            merged.append(pseudo)

        merged.extend(improve_suggestions)
        return merged

    def _combine_outputs(self, review_data: dict, review_tool: PRReviewer,
                          suggestions: List[dict], improve_tool: PRCodeSuggestions) -> str:
        """Format review + suggestions into a single merged markdown string."""
        gfm_supported = self.git_provider.is_supported("gfm_markdown")
        files = self.git_provider.get_diff_files()

        review_data_copy = copy.deepcopy(review_data)

        # Extract review issues and REMOVE from review section (they go in the merged table)
        review_issues = []
        if 'review' in review_data_copy and 'key_issues_to_review' in review_data_copy['review']:
            review_issues = review_data_copy['review'].pop('key_issues_to_review', [])

        # Render review (without key_issues_to_review)
        review_md = convert_to_markdown_v2(
            review_data_copy,
            gfm_supported=gfm_supported,
            git_provider=self.git_provider,
            files=files
        )

        # Convert Estimated effort from numeric+bars to text label
        effort_labels = {'1': 'Very Low', '2': 'Low', '3': 'Medium', '4': 'High', '5': 'Very High'}
        review_md = re.sub(
            r'(Estimated effort to review[^:]*:\s*)(\d)(?:\s*[🔵⚪]+)',
            lambda m: m.group(1) + effort_labels.get(m.group(2), m.group(2)),
            review_md
        )

        # Override the default header to indicate combined output
        combined_header = "## PR Review & Code Suggestions 🔍✨\n\n"
        original_header = f"{PRReviewHeader.REGULAR.value} 🔍\n\n"
        if review_md.startswith(original_header):
            review_md = combined_header + review_md[len(original_header):]

        # Set review labels (effort, security) from the review data
        review_tool.set_review_labels(review_data)

        # Build merged suggestions: review issues (with code context) + improve suggestions
        merged = self._build_merged_suggestions(review_issues, files, suggestions)

        # --- Merged suggestions table (review issues + improve suggestions) ---
        if merged and improve_tool:
            suggestions_md = improve_tool.generate_summarized_suggestions(
                {'code_suggestions': merged}
            )
            # Remove the separate "PR Code Suggestions ✨" header
            if suggestions_md.startswith("## PR Code Suggestions ✨"):
                suggestions_md = suggestions_md[len("## PR Code Suggestions ✨\n\n"):]
            # Remove "Explore these optional code suggestions:" if present in auto mode
            if get_settings().config.is_auto_command:
                suggestions_md = suggestions_md.replace(
                    "Explore these optional code suggestions:\n\n", ""
                )
            review_md += "\n\n" + suggestions_md

        # --- Help text ---
        if gfm_supported and get_settings().pr_reviewer.get('enable_help_text', True):
            review_md += (
                "\n\n<hr>\n\n"
                "<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr>\n\n"
            )
            review_md += HelpMessage.get_review_usage_guide()
            review_md += "\n</details>\n"

        # --- Relevant configs ---
        if get_settings().get('config', {}).get('output_relevant_configurations', False):
            review_md += show_relevant_configurations(relevant_section='pr_reviewer')

        return review_md

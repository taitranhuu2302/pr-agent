# Hướng dẫn Setup và Cấu hình PR-Agent

## Giới thiệu

[PR-Agent](https://github.com/the-pr-agent/pr-agent) là công cụ mã nguồn mở giúp review pull request tự động bằng AI. Nó hỗ trợ nhiều nền tảng git (GitHub, GitLab, Bitbucket, Azure DevOps, Gitea) và có thể chạy local, qua Docker, GitHub Action, hoặc webhook server.

---

## 1. Yêu cầu

- **Python** >= 3.12
- **API Key** từ một LLM provider (OpenAI, Anthropic, v.v.)
- **Token** từ git platform (GitHub PAT, GitLab token, ...)

---

## 2. Các cách setup

### 2.1. Cài đặt qua pip (đơn giản nhất)

```bash
pip install pr-agent
```

Chạy trực tiếp CLI:

```bash
export OPENAI__KEY=sk-...               # double underscore → settings.openai.key
export GITHUB__USER_TOKEN=ghp_...       # double underscore → settings.github.user_token

pr-agent --pr_url https://github.com/owner/repo/pull/123 review
```

Hoặc dùng Python script:

```python
from pr_agent import cli
from pr_agent.config_loader import get_settings

def main():
    get_settings().set("CONFIG.git_provider", "github")
    get_settings().set("openai.key", "sk-...")
    get_settings().set("github.user_token", "ghp_...")

    cli.run_command("https://github.com/owner/repo/pull/123", "/review")

if __name__ == '__main__':
    main()
```

### 2.2. Chạy từ source (development)

```bash
# 1. Clone repo
git clone https://github.com/the-pr-agent/pr-agent.git
cd pr-agent

# 2. Tạo virtualenv (bắt buộc Python ≥ 3.12)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Cài đặt dependencies
pip install -e .

# 4. Copy file secrets template
cp pr_agent/settings/.secrets_template.toml pr_agent/settings/.secrets.toml

# 5. Sửa file .secrets.toml — điền API key và token

# 6. Chạy thử
python -m pr_agent.cli --pr_url <pr_url> review
python -m pr_agent.cli --pr_url <pr_url> describe
python -m pr_agent.cli --pr_url <pr_url> improve
```

### 2.3. Chạy qua Docker

```bash
docker run --rm -it \
  -e OPENAI__KEY=sk-... \
  -e GITHUB__USER_TOKEN=ghp_... \
  pragent/pr-agent:latest \
  --pr_url https://github.com/owner/repo/pull/123 review
```

### 2.4. Dùng GitHub Action

Tạo file `.github/workflows/pr-agent.yml` — dưới đây là các mẫu cho từng provider.

#### Custom OpenAI-compatible endpoint

```yaml
name: PR Agent
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  pr_agent_job:
    runs-on: ubuntu-latest
    steps:
      - name: PR Agent action step
        uses: the-pr-agent/pr-agent@main
        env:
          # === API key ===
          OPENAI_KEY: ${{ secrets.OPENAI_KEY }}

          # === Git token (GitHub tự cung cấp sẵn) ===
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

          # === Custom endpoint (OpenAI-compatible) ===
          OPENAI__API_BASE: ${{ secrets.OPENAI_API_BASE }}

          # === Model config ===
          CONFIG__MODEL: "gpt-5.5-2026-04-23"
          CONFIG__FALLBACK_MODELS: '["gpt-5.4-mini"]'
          # CONFIG__CUSTOM_MODEL_MAX_TOKENS: 128000   # bỏ comment nếu dùng model lạ
```

> **Thiết lập GitHub Secrets:** Vào **Settings → Secrets and variables → Actions**, thêm:
> - `OPENAI_KEY` — API key
> - `OPENAI_API_BASE` — Endpoint URL, vd: `https://api.openai.com/v1`
> - `GITHUB_TOKEN` — có sẵn, không cần tạo

#### Ollama (model local / self-hosted)

```yaml
- name: PR Agent action step
  uses: the-pr-agent/pr-agent@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    CONFIG__MODEL: "ollama/qwen2.5-coder:32b"
    CONFIG__FALLBACK_MODELS: '["ollama/qwen2.5-coder:32b"]'
    CONFIG__CUSTOM_MODEL_MAX_TOKENS: 128000
    OLLAMA__API_BASE: "http://your-ollama-host:11434"
```

#### Anthropic Claude

```yaml
- name: PR Agent action step
  uses: the-pr-agent/pr-agent@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    CONFIG__MODEL: "anthropic/claude-sonnet-4-20250514"
    CONFIG__FALLBACK_MODELS: '["anthropic/claude-sonnet-4-20250514"]'
    ANTHROPIC__KEY: ${{ secrets.ANTHROPIC_KEY }}
```

#### OpenRouter

```yaml
- name: PR Agent action step
  uses: the-pr-agent/pr-agent@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    CONFIG__MODEL: "openrouter/anthropic/claude-3.7-sonnet"
    CONFIG__FALLBACK_MODELS: '["openrouter/deepseek/deepseek-chat"]'
    CONFIG__CUSTOM_MODEL_MAX_TOKENS: 20000
    OPENROUTER__KEY: ${{ secrets.OPENROUTER_KEY }}
    OPENROUTER__API_BASE: "https://openrouter.ai/api/v1"
```

#### Azure OpenAI

```yaml
- name: PR Agent action step
  uses: the-pr-agent/pr-agent@main
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    OPENAI__KEY: ${{ secrets.AZURE_OPENAI_KEY }}
    OPENAI__API_TYPE: "azure"
    OPENAI__API_BASE: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    OPENAI__API_VERSION: "2023-05-15"
    OPENAI__DEPLOYMENT_ID: "gpt-4o"
    CONFIG__MODEL: "gpt-4o"
```

> **Lưu ý:** `FALLBACK_MODELS` dùng list kiểu JSON string: `'["model1", "model2"]'`.

### 2.5. Chạy server webhook

PR-Agent có thể chạy như một server webhook (GitHub App, GitLab webhook, Bitbucket app). Xem hướng dẫn chi tiết tại [`pr_agent/servers/`](../../pr_agent/servers).

---

## 3. Cấu hình

### 3.1. Kiến trúc cấu hình

PR-Agent dùng **Dynaconf** để quản lý cấu hình. Thứ tự ưu tiên (sau ghi đè trước):

1. Environment variables (`OPENAI__KEY=...`)
2. `.secrets.toml` — chứa secret (key, token)
3. `configuration.toml` — mặc định toàn cục
4. `.pr_agent.toml` — per-repo override (đọc từ repo được review)
5. CLI arguments (`--openai.key=...`)

File `.secrets.toml` không được commit lên git (đã có trong `.gitignore`).

### 3.2. File cấu hình chính

| File | Vai trò |
|------|---------|
| `pr_agent/settings/configuration.toml` | Cấu hình gốc — tất cả options mặc định |
| `pr_agent/settings/.secrets.toml` | API keys, tokens (gitignore) |
| `pr_agent/settings/.secrets_template.toml` | Template cho .secrets.toml |
| `.pr_agent.toml` | Cấu hình riêng cho từng repo |

### 3.3. Cấu hình model

#### Mặc định (OpenAI)

Mặc định PR-Agent dùng `gpt-5.5-2026-04-23`. Cấu hình trong `configuration.toml`:

```toml
[config]
model = "gpt-5.5-2026-04-23"
fallback_models = ["gpt-5.4-mini"]
```

#### Custom OpenAI-compatible endpoint

Dùng file `.secrets.toml`:

```toml
[openai]
api_base = "https://your-custom-endpoint.com/v1"
key = "sk-your-api-key"
```

Hoặc environment variables:

```bash
export OPENAI__API_BASE=https://your-custom-endpoint.com/v1
export OPENAI__KEY=sk-your-api-key
```

Hoặc CLI:

```bash
python -m pr_agent.cli --pr_url <url> review \
  --openai.api_base "https://your-custom-endpoint.com/v1" \
  --openai.key "sk-your-api-key"
```

#### Azure OpenAI

```toml
[openai]
key = ""                # Azure API key
api_type = "azure"
api_version = "2023-05-15"
api_base = "https://<resource>.openai.azure.com"
deployment_id = ""      # Tên deployment
```

#### Anthropic (Claude)

```toml
[config]
model = "anthropic/claude-sonnet-4-20250514"
fallback_models = ["anthropic/claude-sonnet-4-20250514"]

[anthropic]
key = "sk-ant-..."
```

#### Ollama (model local)

```toml
[config]
model = "ollama/qwen2.5-coder:32b"
fallback_models = ["ollama/qwen2.5-coder:32b"]
custom_model_max_tokens = 128000

[ollama]
api_base = "http://localhost:11434"
```

#### Groq

```toml
[config]
model = "llama3-70b-8192"
fallback_models = ["groq/llama3-70b-8192"]

[groq]
key = "gsk-..."
```

#### xAI (Grok)

```toml
[config]
model = "xai/grok-2-latest"
fallback_models = ["xai/grok-2-latest"]

[xai]
key = "xai-..."
```

#### DeepSeek

```toml
[config]
model = "deepseek/deepseek-v4-pro"
fallback_models = ["deepseek/deepseek-v4-flash"]

[deepseek]
key = "sk-..."
```

#### OpenRouter

```toml
[config]
model = "openrouter/anthropic/claude-3.7-sonnet"
fallback_models = ["openrouter/deepseek/deepseek-chat"]
custom_model_max_tokens = 20000

[openrouter]
key = "sk-or-..."
api_base = "https://openrouter.ai/api/v1"
```

#### Custom model (không có trong danh sách mặc định)

Xem danh sách model hỗ trợ tại [`pr_agent/algo/__init__.py`](../../pr_agent/algo/__init__.py).

```toml
[config]
model = "my-custom-model"
fallback_models = ["my-custom-model"]
custom_model_max_tokens = 32000       # Giới hạn token input
custom_reasoning_model = true         # true nếu là reasoning model không support chat template
```

### 3.4. Cấu hình git provider

#### GitHub

```toml
[config]
git_provider = "github"
```

```toml
# .secrets.toml
[github]
user_token = "ghp_..."
deployment_type = "user"    # hoặc "app" cho GitHub App
```

#### GitLab

```toml
[config]
git_provider = "gitlab"
```

```toml
[gitlab]
personal_access_token = "glpat-..."
```

#### Bitbucket

```toml
[config]
git_provider = "bitbucket"  # hoặc "bitbucket_server"
```

```toml
[bitbucket]
auth_type = "bearer"        # hoặc "basic"
bearer_token = "..."
```

#### Azure DevOps

```toml
[config]
git_provider = "azure_devops"
```

```toml
[azure_devops]
org = "your-org"
pat = "..."                 # Personal Access Token
```

#### Gitea

```toml
[config]
git_provider = "gitea"
```

```toml
[gitea]
personal_access_token = "..."
url = "https://gitea.your-domain.com"
```

### 3.5. Cấu hình tool

Mỗi tool có section riêng trong `configuration.toml`.

#### /review

```toml
[pr_reviewer]
require_score_review = false
require_tests_review = true
require_security_review = true
num_max_findings = 3
persistent_comment = true
extra_instructions = ""
```

#### /describe

```toml
[pr_description]
extra_instructions = ""
publish_description_as_comment = false
```

#### /improve

```toml
[pr_code_suggestions]
extra_instructions = ""
num_code_suggestions = 4
```

### 3.6. Environment variables

Dùng double underscore `__` để map sang nested key:

```bash
# Tương đương [config].model
export CONFIG__MODEL="gpt-5.5-2026-04-23"

# Tương đương [openai].api_base
export OPENAI__API_BASE="https://api.openai.com/v1"

# Tương đương [github].user_token
export GITHUB__USER_TOKEN="ghp_..."

# Tương đương [config].git_provider
export CONFIG__GIT_PROVIDER="gitlab"
```

Có thể dùng file `.env` với Docker:

```bash
CONFIG__GIT_PROVIDER="gitlab"
GITLAB__URL="https://gitlab.your-company.com"
GITLAB__PERSONAL_ACCESS_TOKEN="glpat-..."
OPENAI__KEY="sk-..."
```

```bash
docker run --rm -it --env-file .env pragent/pr-agent:latest review --pr_url <url>
```

### 3.7. Cấu hình per-repo (`.pr_agent.toml`)

Tạo file `.pr_agent.toml` trong thư mục gốc của repo được review:

```toml
[config]
model = "anthropic/claude-sonnet-4-20250514"
response_language = "vi-VN"

[pr_reviewer]
num_max_findings = 5
extra_instructions = "Tập trung vào security issues."
```

File này được đọc và merge tự động khi PR-Agent xử lý PR từ repo đó.

---

## 4. Các lệnh CLI

```bash
# Review PR
pr-agent --pr_url <pr_url> review

# Mô tả PR
pr-agent --pr_url <pr_url> describe

# Đề xuất cải thiện code
pr-agent --pr_url <pr_url> improve

# Hỏi về PR
pr-agent --pr_url <pr_url> ask "Câu hỏi của bạn?"

# Thêm documentation
pr-agent --pr_url <pr_url> add_docs

# Generate labels
pr-agent --pr_url <pr_url> generate_labels

# Similar issues
pr-agent --issue_url <issue_url> similar_issue
```

Khi chạy từ source:

```bash
python -m pr_agent.cli --pr_url <pr_url> review
```

---

## 5. Troubleshooting

### Lỗi "Connection error" từ litellm

Litellm đôi khi trả về lỗi `APIError: OpenAIException - Connection error` không rõ ràng. Kiểm tra:

- API key và endpoint đã đúng chưa?
- Với Azure: đã set `api_type = "azure"` và `deployment_id` chưa?
- Với Ollama: context window có đủ không? Set `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`

### Lỗi "cannot import name" khi cài đặt

Lỗi Rust trong dependency: cài Rust từ https://rustup.rs/

### Model không sinh được structured output

Set `duplicate_prompt_examples = true` trong `[config]` và tăng `custom_model_max_tokens`.

### Timeout khi xử lý PR lớn

Tăng `ai_timeout` trong `[config]`:

```toml
[config]
ai_timeout = 300  # 5 phút
```

---

## 6. Tham khảo

- [Cấu hình chi tiết (configuration.toml)](../../pr_agent/settings/configuration.toml)
- [Secrets template](../../pr_agent/settings/.secrets_template.toml)
- [Danh sách model hỗ trợ](../../pr_agent/algo/__init__.py)
- [Litellm providers](https://docs.litellm.ai/docs/providers)
- [Tài liệu PR-Agent đầy đủ](https://docs.pr-agent.ai/)

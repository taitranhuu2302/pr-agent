# Hướng dẫn Setup PR-Agent với OpenCode (DeepSeek V4 Flash)

## Thông tin

| Mục | Giá trị |
|-----|---------|
| Provider | OpenCode AI |
| Model | `deepseek-v4-flash` |
| Endpoint | `https://opencode.ai/zen/go/v1` |
| Giao thức | OpenAI-compatible |

---

## 1. Yêu cầu

- Python >= 3.12 (khuyên dùng 3.12 hoặc 3.13)
- API key từ [opencode.ai](https://opencode.ai)

---

## 2. Setup

### 2.1. Clone & cài đặt

```powershell
# Clone repo
git clone https://github.com/the-pr-agent/pr-agent.git
cd pr-agent

# Tạo virtualenv với Python 3.12
py -3.12 -m venv .venv

# Activate
.venv\Scripts\activate

# Cài dependencies
pip install -e .
```

### 2.2. Cấu hình `.secrets.toml`

Sửa file `pr_agent/settings/.secrets.toml`:

```toml
[openai]
api_base = "https://opencode.ai/zen/go/v1"
key = "sk-your-opencode-api-key"         # key, không phải api_key
```

### 2.3. Cấu hình model (env var)

```powershell
$env:CONFIG__MODEL = "deepseek-v4-flash"
$env:CONFIG__CUSTOM_MODEL_MAX_TOKENS = "128000"
$env:CONFIG__PUBLISH_OUTPUT = "false"     # false = chỉ in terminal, không comment lên PR
```

> **Lưu ý về api_base:** Chỉ nhập tới `/v1`, **không** gồm `/chat/completions`. Litellm tự thêm phần này.

---

## 3. Chạy

### 3.1. Với private repo — cần token GitHub

```powershell
$env:GITHUB__USER_TOKEN = "ghp_..."
python -m pr_agent.cli --pr_url https://github.com/owner/repo/pull/1 review
```

### 3.2. Tất cả trong một lệnh (PowerShell)

```powershell
$env:OPENAI__API_BASE = "https://opencode.ai/zen/go/v1"
$env:OPENAI__KEY = "sk-your-opencode-api-key"
$env:CONFIG__MODEL = "deepseek-v4-flash"
$env:CONFIG__CUSTOM_MODEL_MAX_TOKENS = "128000"
$env:GITHUB__USER_TOKEN = "ghp_..."

python -m pr_agent.cli --pr_url https://github.com/owner/repo/pull/1 review
```

---

## 4. GitHub Action

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
          OPENAI_KEY: ${{ secrets.OPENSCODE_API_KEY }}
          OPENAI__API_BASE: "https://opencode.ai/zen/go/v1"
          CONFIG__MODEL: "deepseek-v4-flash"
          CONFIG__CUSTOM_MODEL_MAX_TOKENS: 128000
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Thêm secret `OPENSCODE_API_KEY` vào **Settings → Secrets and variables → Actions**.

---

## 5. File `.pr_agent.toml` (per-repo config)

Tạo file này trong thư mục gốc của repo bạn muốn review:

```toml
[config]
model = "deepseek-v4-flash"
custom_model_max_tokens = 128000
response_language = "vi-VN"

[pr_reviewer]
num_max_findings = 5
extra_instructions = "Tập trung vào security issues."
```

---

## 6. Troubleshooting

### Lỗi "404 Not Found"

Kiểm tra `api_base` — phải là `/v1` không kèm `/chat/completions`:

```toml
# Sai ❌
api_base = "https://opencode.ai/zen/go/v1/chat/completions"

# Đúng ✅
api_base = "https://opencode.ai/zen/go/v1"
```

### Lỗi "Connection error"

- Kiểm tra API key còn hiệu lực
- Endpoint có reachable không?

### Lỗi model không sinh được output

Tăng `custom_model_max_tokens` lên `128000` hoặc cao hơn.

---

## 7. Tham khảo

- [PR-Agent Docs](https://docs.pr-agent.ai/)
- [OpenCode AI](https://opencode.ai)
- [LiteLLM Providers](https://docs.litellm.ai/docs/providers)

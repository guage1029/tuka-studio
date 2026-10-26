# OpenAI API 配置
# 支持 OpenAI 官方 API 或兼容的第三方服务（如 DeepSeek、Gemini）

# === 选项 1: OpenAI 官方 ===
# OPENAI_BASE_URL = "https://api.openai.com/v1"
# OPENAI_API_KEY = "sk-..."
# MODEL_NAME = "gpt-4o"

# === 选项 2: DeepSeek ===
# OPENAI_BASE_URL = "https://api.deepseek.com"
# OPENAI_API_KEY = "sk-..."
# MODEL_NAME = "deepseek-chat"

# === 选项 3: Google Gemini (原生 SDK) ===
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # 请替换为你的 Gemini API Key
MODEL_NAME = "models/gemini-2.5-flash-lite"  # 推荐使用 lite 版本

# 图片尺寸配置（小红书 3:4 比例）
IMAGE_WIDTH = 1242
IMAGE_HEIGHT = 1660

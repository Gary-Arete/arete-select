# ----- build runtime -----
FROM python:3.11-slim

# 讓 Python 不緩存、日誌即時輸出
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 系統套件（時區/字型可略）
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales && rm -rf /var/lib/apt/lists/*

# 建立工作目錄
WORKDIR /app

# 複製需求與程式
# 你的需求檔叫 "requirements"（沒有 .txt），我們兩種都處理
COPY requirements /app/requirements 2>/dev/null || true
COPY requirements.txt /app/requirements.txt 2>/dev/null || true
RUN if [ -f /app/requirements ]; then pip install -r /app/requirements; \
    elif [ -f /app/requirements.txt ]; then pip install -r /app/requirements.txt; \
    else pip install Flask gspread oauth2client; fi

# 複製整個 repo（含子資料夾）
COPY . /app

# 直接切換到子資料夾（處理空白目錄名）
WORKDIR "/app/Arete Select"

# 用 gunicorn 啟動（較穩定），app 物件在 main.py 裡的 "app"
# 若想先用 python 直跑也可：CMD ["python", "main.py"]
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]

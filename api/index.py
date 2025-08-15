# api/index.py
import sys, os
from pathlib import Path

# 把「Arete Select」放進匯入路徑（資料夾名稱有空白沒關係）
sys.path.append(str(Path(__file__).resolve().parents[1] / 'Arete Select'))

# 從你原本的 main.py 匯入 Flask app（main.py 裡已有 app = Flask(__name__)）
from main import app  # Vercel 會直接使用這個 app

# 注意：這個檔案不要寫 app.run()，Vercel 會接管執行

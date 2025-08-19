# find_pdf_fields.py
from pypdf import PdfReader

# 確保這個路徑指向您專案中的 PDF 範本
pdf_path = 'core/pdf_templates/ir56b_ay.pdf'

try:
    reader = PdfReader(pdf_path)
    # get_fields() 會回傳一個包含所有欄位資訊的字典
    fields = reader.get_fields()

    if not fields:
        print("錯誤：在這個 PDF 中找不到任何可填寫的欄位。請確認 PDF 是否為可填寫的表單。")
    else:
        print("--- PDF 表單的真實欄位列表 ---")
        # 遍歷並印出每一個欄位的名稱
        for field_name in fields:
            print(f"'{field_name}'") # 我們用引號括起來，方便複製
        print("---------------------------------")
        print("\n請將上面引號內的欄位名稱，複製並替換到 views.py 的 data_to_fill 字典中對應的鍵 (key)。")

except FileNotFoundError:
    print(f"錯誤：找不到 PDF 檔案，請確認路徑 '{pdf_path}' 是否正確。")
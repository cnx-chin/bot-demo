import csv
import io
import datetime

def generate_csv_filename(store_code: str, title: str):
    """
    GCSにアップロードするためのCSVファイル名を動的に生成する。
    フォーマット: YYYY/MM/YYYYMMDDHHMMSS_店舗コード_出納票種類.csv

    Args:
        store_code (str): 店舗コード。
        title (str): 出納票の種類。

    Returns:
        str: 生成された完全なファイルパス。
    """
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now_jst = datetime.datetime.now(jst)
    
    # タイムスタンプ部分のファイル名を生成
    timestamp_str = now_jst.strftime('%Y%m%d%H%M%S')
    
    # titleに含まれる可能性のある不正なファイル名文字を置換
    # 例: '/' や ' ' などを '_' に置換
    safe_title = title.replace('/', '_').replace(' ', '_').replace('　', '_') if title else "NoTitle"

    base_filename = f"{timestamp_str}_{store_code}_{safe_title}.csv"
    
    # フォルダパスとファイル名を結合して完全なGCSオブジェクト名を返す
    return base_filename


def generate_csv_content(parsed_data: dict):
    """
    解析済みのデータ辞書からCSVファイルの内容（文字列）を生成する。
    「項目」と「金額」の2列のみを出力する。

    Args:
        parsed_data (dict): doc_ai_parserから返された解析済みデータ。

    Returns:
        tuple: (CSV文字列, エラーメッセージ)
    """

    output = io.StringIO()
    
    # CSVのヘッダーを「項目」と「金額」のみに限定
    fieldnames = ['項目', '金額']
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator='\r\n')
    writer.writeheader()
    
    # 'line_items' が存在し、かつ空でない場合のみ、行を書き込む
    if parsed_data and parsed_data.get('line_items'):
        for item_detail in parsed_data['line_items']:
            writer.writerow({
                '項目': item_detail.get('item', ''),
                '金額': item_detail.get('amount', '')
            })
        
    # 文字列としてCSVの内容を返す
    return output.getvalue(), None
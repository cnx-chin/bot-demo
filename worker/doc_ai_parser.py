import logging
from google.cloud import documentai
from collections import defaultdict
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
import config

# --- データ構造を定義 ---

@dataclass
class ParsedEntity:
    """Document AIのエンティティから抽出した、扱いやすい中間データ構造。"""
    text: str
    type: str
    center_y: float
    center_x: float
    x_min: float
    x_max: float
    height: float

    def __repr__(self):
        return f"({self.type}: '{self.text}', y={self.center_y:.4f}, x={self.center_x:.4f})"

# --- ヘルパー関数 ---

def _create_parsed_entity(entity: documentai.Document.Entity) -> Optional[ParsedEntity]:
    """安全にParsedEntityオブジェクトを作成する。"""
    try:
        if not entity.page_anchor.page_refs: return None
        vertices = entity.page_anchor.page_refs[0].bounding_poly.normalized_vertices
        if not vertices or len(vertices) < 4: return None
        
        x_coords = [v.x for v in vertices if v.x is not None]
        y_coords = [v.y for v in vertices if v.y is not None]
        if not x_coords or not y_coords: return None

        y_min, y_max = min(y_coords), max(y_coords)
        x_min, x_max = min(x_coords), max(x_coords)
        
        return ParsedEntity(
            text=entity.mention_text.replace('\n', ''),
            type=entity.type_,
            center_y=(y_min + y_max) / 2,
            center_x=(x_min + x_max) / 2,
            x_min=x_min,
            x_max=x_max,
            height=(y_max - y_min)
        )
    except (AttributeError, IndexError, ValueError):
        return None

def _calculate_dynamic_tolerance(entities: List[ParsedEntity]) -> float:
    """異常値を除外して、より安定したY座標の許容誤差を動的に計算する。"""
    if not entities: return 0.01
    heights = sorted([entity.height for entity in entities if entity.height > 0.001])
    if not heights: return 0.01

    stable_start_index = len(heights) // 5
    stable_end_index = len(heights) * 4 // 5
    stable_heights = heights[stable_start_index:stable_end_index]
    if not stable_heights: stable_heights = heights

    avg_height = sum(stable_heights) / len(stable_heights)
    
    # 許容誤差を平均的な文字の高さの半分（より保守的）に設定
    tolerance = max(avg_height * 0.95, 0.008)
    logging.info(f"動的なY座標の許容誤差を計算しました: {tolerance:.4f} (平均高さ: {avg_height:.4f})")
    return tolerance

def _group_entities_by_row(entities: List[ParsedEntity], y_tolerance: float) -> List[List[ParsedEntity]]:
    """隣接ベースのアルゴリズムで、全てのエンティティを行に分割する。"""
    if not entities: return []

    sorted_entities = sorted(entities, key=lambda e: e.center_y)
    
    groups = []
    current_group = [sorted_entities[0]]

    for i in range(1, len(sorted_entities)):
        # 基準となるY座標は、グループの最初の要素のものに固定する
        group_base_y = current_group[0].center_y
        current_entity = sorted_entities[i]

        if abs(current_entity.center_y - group_base_y) < y_tolerance:
            current_group.append(current_entity)
        else:
            groups.append(current_group)
            current_group = [current_entity]
    
    groups.append(current_group)

    logging.info(f"エンティティを行に分割しました: {len(groups)}行")
    for i, group in enumerate(groups):
        logging.info(f"  行{i+1}: {group}")
        
    return groups

def _normalize_title(raw_title: str) -> str:
    """
    タイトルを原子レベルのファジーマッチングで正規化する。
    特徴文字の組み合わせ（AND条件）と排他制御により、
    誤読（例: 'ッ払', '出納表(クレジット支払)'）を正しいキーワードに補正する。
    """
    if not raw_title:
        return raw_title

    # 特徴文字の含有チェック
    has_credit = any(c in raw_title for c in config.CREDIT_CHARS)
    has_cash = any(c in raw_title for c in config.CASH_CHARS)
    has_payment = any(c in raw_title for c in config.PAYMENT_CHARS)
    has_receipt = any(c in raw_title for c in config.RECEIPT_CHARS)

    normalized_title = raw_title

    # 組み合わせ判定 (互斥チェック付き)
    if has_credit and not has_cash:
        if has_payment and not has_receipt:
            normalized_title = "クレジット支払"
        elif has_receipt and not has_payment:
            normalized_title = "クレジット受入"
    elif has_cash and not has_credit:
        if has_payment and not has_receipt:
            normalized_title = "現金支払"
        elif has_receipt and not has_payment:
            normalized_title = "現金受入"
    
    if normalized_title != raw_title:
        logging.info(f"タイトル正規化成功: '{raw_title}' -> '{normalized_title}'")
    
    return normalized_title

# --- メインの解析関数 ---
def parse_document_entities(document: documentai.Document):
    """
    Document AIのエンティティを解析し、項目と金額をペアリングする。
    項目と金額の数が一致する場合は順序に基づいてペアリングし、
    一致しない場合はY座標ベースの行グルーピングでペアリングを試みる。
    """
    logging.info("--- スマート解析モジュール開始 ---")

    # 【ステップ1: 前処理】
    item_entities: List[ParsedEntity] = []
    amount_entities: List[ParsedEntity] = []
    extracted_data = {"title": None, "shop_name": None, "date": None, "line_items": []}

    for entity in document.entities:
        if entity.type_ in ['item', 'amount']:
            parsed_entity = _create_parsed_entity(entity)
            if parsed_entity:
                if entity.type_ == 'item':
                    item_entities.append(parsed_entity)
                elif entity.type_ == 'amount':
                    amount_entities.append(parsed_entity)
        elif entity.type_ in extracted_data and extracted_data[entity.type_] is None:
            raw_text = entity.mention_text.replace('\n', '')
            if entity.type_ == 'title':
                extracted_data[entity.type_] = _normalize_title(raw_text)
            else:
                extracted_data[entity.type_] = raw_text

    line_items = []
    is_review_needed = False

    # 【ステップ2: 解析戦略の分岐】
    # 項目と金額の数が一致し、かつ0でない場合、単純な順序ベースのマッチングを試みる
    if item_entities and len(item_entities) == len(amount_entities):
        logging.info(f"項目と金額の数が一致 ({len(item_entities)}個)。順序ベースのペアリングを実行します。")
        
        # Y座標でソートして、上から順にペアリングする
        sorted_items = sorted(item_entities, key=lambda e: e.center_y)
        sorted_amounts = sorted(amount_entities, key=lambda e: e.center_y)

        for i in range(len(sorted_items)):
            item = sorted_items[i]
            amount = sorted_amounts[i]
            
            final_item_text = item.text.replace(' ', '').replace('　', '').replace('@', '(a)')
            final_amount_text = re.sub(r'[^0-9]', '', amount.text)

            #クリーニング後のテキストをそのまま追加する。
            line_items.append({'item': final_item_text, 'amount': final_amount_text})
    
    else:
        # 項目と金額の数が一致しない場合、従来の座標ベースの行グルーpingを実行
        logging.info(f"項目({len(item_entities)}個)と金額({len(amount_entities)}個)の数が不一致。座標ベースの行グルーピングを実行します。")
        all_entities = item_entities + amount_entities
        if not all_entities:
            logging.warning("解析対象の項目または金額エンティティが見つかりませんでした。")
            extracted_data['line_items'] = []
            return extracted_data, False, None # レビューは不要

        y_tolerance = _calculate_dynamic_tolerance(all_entities)

        # 【ステップ3: 行分割】
        row_groups = _group_entities_by_row(all_entities, y_tolerance)

        # 【ステップ4: 行ごとの解析とペアリング】
        for row in row_groups:
            row_items = [entity for entity in row if entity.type == 'item']
            row_amounts = [entity for entity in row if entity.type == 'amount']

            row_items.sort(key=lambda e: e.center_x)
            row_amounts.sort(key=lambda e: e.center_x)

            merged_item_text = ' '.join(item.text for item in row_items)
            final_item_text = merged_item_text.replace(' ', '').replace('　', '').replace('@', '(a)')

            final_amount_text = ''
            if len(row_items) > 0 and len(row_amounts) > 0:
                if row_items[-1].x_max < row_amounts[0].x_min:
                    merged_amount_text = ' '.join(amount.text for amount in row_amounts)
                    final_amount_text = re.sub(r'[^0-9]', '', merged_amount_text)
                else:
                    logging.warning(f"行内でのX座標の重なりを検出。項目: '{merged_item_text}', 金額: {[a.text for a in row_amounts]}。この行の金額は無視されます。")
                    final_amount_text = '' 
                    is_review_needed = True
            elif len(row_amounts) > 0:
                merged_amount_text = ' '.join(amount.text for amount in row_amounts)
                final_amount_text = re.sub(r'[^0-9]', '', merged_amount_text)

            if final_item_text and final_amount_text:
                line_items.append({'item': final_item_text, 'amount': final_amount_text})
            elif final_item_text and not final_amount_text:
                line_items.append({'item': final_item_text, 'amount': '0'})
                is_review_needed = True
            elif not final_item_text and final_amount_text:
                line_items.append({'item': '項目不明', 'amount': final_amount_text})
                is_review_needed = True

    # 【ステップ5: 最終結果の組み立て】
    extracted_data['line_items'] = line_items
    
    # --- ユーザー警告メッセージの生成 ---
    user_warning = None
    if is_review_needed and line_items:
        item_count = len(line_items)
        if item_count >= 3:
            user_warning = "の写真が傾いているか、手ぶれで読み漏れが発生しました。もう一度撮影してアップロードするか、テレマスにて手修正してください。"
        else:
            user_warning = "の写真が傾いているか、手ぶれで読み漏れが発生しました。テレマスにて手修正してください。"

    logging.info(f"スマート解析完了。抽出データ: {extracted_data}")
    logging.info(f"この帳票はレビューが必要か: {is_review_needed}")
    if user_warning:
        logging.info(f"ユーザー警告: {user_warning}")
    
    return extracted_data, is_review_needed, user_warning
import cv2
import numpy as np
import io
import logging
from typing import Optional, Tuple
from PIL import Image, ImageOps

# ==========================================
# 基本ユーティリティクラス：画像処理の原子操作
# ==========================================
class ImageUtils:
    @staticmethod
    def to_gray(img: np.ndarray) -> np.ndarray:
        """グレースケール画像に変換する"""
        if len(img.shape) == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img.copy()

    @staticmethod
    def rotate_image(img: np.ndarray, angle_code: int) -> np.ndarray:
        """回転操作を実行する"""
        if angle_code == cv2.ROTATE_90_CLOCKWISE:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle_code == cv2.ROTATE_180:
            return cv2.rotate(img, cv2.ROTATE_180)
        return img

    @staticmethod
    def remove_shadows(gray_img: np.ndarray) -> np.ndarray:
        """影除去アルゴリズム (入力はグレースケール画像である必要がある)"""
        dilated = cv2.dilate(gray_img, np.ones((7, 7), np.uint8))
        bg = cv2.medianBlur(dilated, 21)
        diff = 255 - cv2.absdiff(gray_img, bg)
        norm = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)
        return norm

# ==========================================
# コアロジック：分析と検出 (読み取り専用、元画像は変更しない)
# ==========================================
class DocAnalyzer:
    @staticmethod
    def get_paper_mask(gray_img: np.ndarray) -> np.ndarray:
        """用紙領域のマスクを取得する"""
        h, w = gray_img.shape
        img_area = h * w
        
        blurred = cv2.GaussianBlur(gray_img, (21, 21), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        mask = np.zeros((h, w), dtype=np.uint8)
        
        if not contours:
            logging.debug("      [Mask] 警告: 輪郭が検出されませんでした。全画面モードに戻ります。")
            mask[:] = 255 
            return mask

        max_cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(max_cnt)
        
        if area < img_area * 0.05:
            logging.debug("      [Mask] 警告: 輪郭が小さすぎます (<5%)。認識失敗と判定し、全画面モードに戻ります。")
            mask[:] = 255
        else:
            cv2.drawContours(mask, [max_cnt], -1, 255, -1)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
            mask = cv2.erode(mask, kernel, iterations=1)
        
        return mask

    @staticmethod
    def analyze_orientation_90(gray_img: np.ndarray, mask: np.ndarray) -> Optional[int]:
        """
        90度回転が必要かどうかを分析する
        戻り値: (回転が必要な場合の角度コード または None)
        """
        logging.info("  -> [Step 1] 90度回転の特徴を分析中...")
        
        # 前処理: マスク適用とリサイズ
        binary = DocAnalyzer._preprocess_for_orientation(gray_img, mask)
        
        # テキスト特徴の抽出
        horizontal_votes, vertical_votes = DocAnalyzer._extract_text_orientation_features(binary)
        
        # 回転判定
        return DocAnalyzer._decide_90_rotation(horizontal_votes, vertical_votes)

    @staticmethod
    def _preprocess_for_orientation(gray_img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """方向分析用の前処理"""
        masked_gray = cv2.bitwise_and(gray_img, gray_img, mask=mask)
        
        h, w = gray_img.shape
        scale = 1600.0 / max(h, w)
        small = cv2.resize(masked_gray, None, fx=scale, fy=scale)
        
        binary = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY_INV, 25, 10)
        return binary

    @staticmethod
    def _extract_text_orientation_features(binary: np.ndarray) -> Tuple[int, int]:
        """テキストの方向特徴を抽出 (横書き票数, 縦書き票数)"""
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        horizontal_votes = 0
        vertical_votes = 0
        img_area = binary.shape[0] * binary.shape[1]
        
        for cnt in contours:
            _, _, cw, ch = cv2.boundingRect(cnt)
            
            # ノイズフィルタリング
            if cw * ch < img_area * 0.0005:
                continue
            if cw > binary.shape[1] * 0.5 or ch > binary.shape[0] * 0.5:
                continue
            
            aspect_ratio = cw / float(ch)
            
            if aspect_ratio > 1.5:
                horizontal_votes += 1
            elif aspect_ratio < 0.7:
                vertical_votes += 1
        
        logging.debug(f"      [投票] 横書き特徴: {horizontal_votes}, 縦書き特徴: {vertical_votes}")
        return horizontal_votes, vertical_votes

    @staticmethod
    def _decide_90_rotation(horizontal_votes: int, vertical_votes: int) -> Optional[int]:
        """投票結果から90度回転の必要性を判定"""
        total_votes = horizontal_votes + vertical_votes
        
        if total_votes < 3:
            logging.debug("      [判定] 特徴不足のため、現状を維持します。")
            return None
        
        if vertical_votes > horizontal_votes * 1.2 or (horizontal_votes == 0 and vertical_votes > 2):
            logging.info("      [結果] 縦書きと判定されました（実際には時計回りに90度回転が必要です）。")
            return cv2.ROTATE_90_CLOCKWISE
        
        return None

    @staticmethod
    def analyze_upside_down_180(gray_img: np.ndarray, mask: np.ndarray) -> Optional[int]:
        """180度回転（逆さま）が必要かどうかを分析する"""
        logging.info("  -> [Step 2] 180度回転の特徴を分析中...")
        
        # ROI領域の計算
        roi_top, roi_bottom = DocAnalyzer._extract_top_bottom_rois(gray_img, mask)
        
        if roi_top is None or roi_bottom is None:
            return None
        
        # インク濃度の比較
        top_ink = DocAnalyzer._calculate_ink_density(roi_top)
        bottom_ink = DocAnalyzer._calculate_ink_density(roi_bottom)
        
        logging.debug(f"      [インク濃度] Top: {top_ink}, Bottom: {bottom_ink}")
        
        if bottom_ink > top_ink * 1.1:
            logging.info("      [結果] 逆さまと判定されました（180度回転が必要です）。")
            return cv2.ROTATE_180
        
        return None

    @staticmethod
    def _extract_top_bottom_rois(gray_img: np.ndarray, mask: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """上部と下部のROI領域を抽出"""
        y_indices, x_indices = np.where(mask > 0)
        if len(y_indices) == 0:
            return None, None
        
        y_min, y_max = np.min(y_indices), np.max(y_indices)
        x_min, x_max = np.min(x_indices), np.max(x_indices)
        h, w = y_max - y_min, x_max - x_min
        
        safe_margin_y = int(h * 0.05)
        safe_margin_x = int(w * 0.1)
        roi_h_size = int(h * 0.45)
        
        roi_top = gray_img[y_min + safe_margin_y : y_min + safe_margin_y + roi_h_size, 
                           x_min + safe_margin_x : x_max - safe_margin_x]
        
        roi_bottom = gray_img[y_max - safe_margin_y - roi_h_size : y_max - safe_margin_y, 
                              x_min + safe_margin_x : x_max - safe_margin_x]
        
        return roi_top, roi_bottom

    @staticmethod
    def _calculate_ink_density(roi: np.ndarray) -> int:
        """ROI領域のインク濃度を計算"""
        if roi.size == 0:
            return 0
        
        clean = ImageUtils.remove_shadows(roi)
        _, binary = cv2.threshold(clean, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return cv2.countNonZero(binary)


def process_image(image_bytes: bytes) -> bytes:
    """
    画像のバイトデータを受け取り、回転・影除去処理を行った結果のバイトデータを返す
    
    Args:
        image_bytes: 元画像のバイトデータ
    
    Returns:
        処理済み画像のバイトデータ (JPEG)
    """
    logging.info("画像処理を開始します (回転補正 & 影除去)...")
    
    try:
        # EXIF修正とOpenCV形式への変換
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        current_color = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        # グレースケール変換
        current_gray = ImageUtils.to_gray(current_color)
        
        # Stage 1: 90度補正
        mask = DocAnalyzer.get_paper_mask(current_gray)
        rotate_cmd = DocAnalyzer.analyze_orientation_90(current_gray, mask)
        
        if rotate_cmd is not None:
            current_color = ImageUtils.rotate_image(current_color, rotate_cmd)
            current_gray = ImageUtils.rotate_image(current_gray, rotate_cmd)
            mask = ImageUtils.rotate_image(mask, rotate_cmd)
        
        # Stage 2: 180度補正
        rotate_cmd_180 = DocAnalyzer.analyze_upside_down_180(current_gray, mask)
        
        if rotate_cmd_180 is not None:
            current_color = ImageUtils.rotate_image(current_color, rotate_cmd_180)
        
        # Stage 3: 影除去
        logging.info("  -> [Step 3] 最終処理中 (影除去)...")
        final_gray = ImageUtils.to_gray(current_color)
        final_output = ImageUtils.remove_shadows(final_gray)
        
        # JPEG エンコード
        success, buffer = cv2.imencode('.jpg', final_output)
        if not success:
            logging.error("処理済み画像のエンコードに失敗しました。")
            return image_bytes
        
        return buffer.tobytes()
    
    except Exception as e:
        logging.error(f"画像処理中にエラーが発生しました: {e}", exc_info=True)
        return image_bytes
import os
import cv2
import numpy as np
import json
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def imread_unicode(file_path):
    """
    한글 경로가 포함된 파일에서도 OpenCV가 한글을 인식하지 못하는 버그를 
    우회하여 안전하게 이미지를 읽어옵니다.
    """
    try:
        file_bytes = np.fromfile(file_path, dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"이미지 읽기 중 오류 발생 ({file_path}): {e}")
        return None

def imwrite_unicode(file_path, img):
    """
    한글 경로가 포함된 경로에도 이미지 형식을 안전하게 인코딩하여 저장합니다.
    """
    try:
        ext = os.path.splitext(file_path)[1]
        # 인코딩 성공 여부 확인
        result, nparr = cv2.imencode(ext, img)
        if result:
            nparr.tofile(file_path)
            return True
        else:
            print(f"이미지 인코딩 실패 ({file_path})")
            return False
    except Exception as e:
        print(f"이미지 저장 중 오류 발생 ({file_path}): {e}")
        return False

def apply_random_effect(roi):
    """
    적용 대상 ROI 이미지에 만화화 필터 또는 자연스러운 색상 변경 필터 중 하나를 랜덤 적용합니다.
    피부색(살색)이나 무채색(저채도 영역)도 확실히 변하도록 채도 강제 보정(Saturation Injection)을 가미합니다.
    """
    effect_type = random.choice(["cartoon", "hue_shift"])
    
    # 원본 ROI의 채도(S) 분석
    hsv_orig = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv_orig)
    s_mean = np.mean(s)
    
    # 60~120도 구간 회전으로 원본과 확연히 대비되는 색상을 획득
    hsv_shift = random.choice([random.randint(60, 120), random.randint(-120, -60)])
    
    if effect_type == "cartoon":
        # 1. 고품질 만화화 필터
        color = roi.copy()
        for _ in range(4):
            color = cv2.bilateralFilter(color, d=7, sigmaColor=20, sigmaSpace=10)
            
        color_hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
        ch, cs, cv = cv2.split(color_hsv)
        
        # 무채색/저채도 및 지나치게 어둡거나 밝은 영역(머리카락, 흰 배경 등) 감지 시 강력한 색조/밝기 주입
        if s_mean < 60:
            # 채도를 대폭 끌어올려 컬러를 강제로 도드라지게 함 (최소 150)
            cs = np.clip(cs.astype(np.float32) + 120, 150, 255).astype(np.uint8)
        if np.mean(cv) < 70:
            # 너무 어두운 경우 밝기를 매우 밝게 올림 (최소 130)
            cv = np.clip(cv.astype(np.float32) + 100, 130, 255).astype(np.uint8)
        elif np.mean(cv) > 180:
            # 너무 밝은 경우 어둡게 낮춤 (최대 120)
            cv = np.clip(cv.astype(np.float32) - 100, 0, 120).astype(np.uint8)
        
        # 카툰화에서도 색상이 쉽게 구분되도록 80% 확률로 색상 회전 추가
        if random.random() < 0.8:
            ch = ((ch.astype(np.int16) + hsv_shift) % 180).astype(np.uint8)
            
        # 기본 카툰 채도 대폭 향상
        cs = np.clip(cs * 1.5, 0, 255).astype(np.uint8)
        
        color_merged = cv2.merge([ch, cs, cv])
        color = cv2.cvtColor(color_merged, cv2.COLOR_HSV2BGR)
        
        # 얇고 부드러운 스케치 선
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray_blur, 50, 150)
        edges = cv2.GaussianBlur(edges, (3, 3), 0)
        
        edge_mask = edges.astype(np.float32) / 255.0
        edge_mask = np.expand_dims(edge_mask, axis=2)
        
        dark_line_color = np.array([50, 55, 75], dtype=np.float32)
        edge_opacity = 0.4
        
        cartoon = (color.astype(np.float32) * (1.0 - edge_mask * edge_opacity) + 
                   dark_line_color * (edge_mask * edge_opacity)).astype(np.uint8)
        return cartoon
        
    else:
        # 2. 사물 색상 변경 (Hue Shift) - 원본 형상 대비 선명한 대조색 부여
        if s_mean < 60:
            # 채도를 대폭 끌어올려 컬러를 강제로 도드라지게 함 (최소 150)
            s = np.clip(s.astype(np.float32) + 120, 150, 255).astype(np.uint8)
        if np.mean(v) < 70:
            # 너무 어두운 경우 밝기를 매우 밝게 올림 (최소 130)
            v = np.clip(v.astype(np.float32) + 100, 130, 255).astype(np.uint8)
        elif np.mean(v) > 180:
            # 너무 밝은 경우 어둡게 낮춤 (최대 120)
            v = np.clip(v.astype(np.float32) - 100, 0, 120).astype(np.uint8)
            
        # 확실한 보색 및 대조 구분을 위해 강제 색조 회전
        h = ((h.astype(np.int16) + hsv_shift) % 180).astype(np.uint8)
        # 기본 채도 및 밝기 추가 조정
        s = np.clip(s * 1.5, 0, 255).astype(np.uint8)
        v = np.clip(v * 1.1 + 10, 0, 255).astype(np.uint8)
        
        merged = cv2.merge([h, s, v])
        return cv2.cvtColor(merged, cv2.COLOR_HSV2BGR)

def get_object_mask(roi):
    """
    ROI 이미지 내부에서 가장 두드러지는 특정 사물/물체 형태의 이진 마스크를 생성합니다.
    외곽선 검출을 통해 박스 형태의 경계선 부자연스러움을 해소합니다.
    """
    h, w = roi.shape[:2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Canny 에지 검출 및 모폴로지 클로즈 연산으로 물체의 대략적 외곽 폐곡선 유도
    edged = cv2.Canny(blurred, 30, 130)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros((h, w), dtype=np.uint8)
    
    if contours:
        # 면적이 넓은 순서대로 외곽선 정렬
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        
        # 전체 ROI 영역의 5% ~ 95% 크기에 달하는 윤곽선 중 가장 큰 실루엣을 타겟팅하여 검출 범위 확대
        roi_area = h * w
        chosen_contour = None
        for c in contours:
            area = cv2.contourArea(c)
            if 0.05 * roi_area < area < 0.95 * roi_area:
                chosen_contour = c
                break
        
        if chosen_contour is not None:
            # 타겟 사물의 내부를 흰색(255)으로 가득 채움
            cv2.drawContours(mask, [chosen_contour], -1, 255, -1)
            return mask

    # 적절한 사물 형태를 검출하지 못했다면 부드러운 중앙 원형(Oval) 마스크로 대체 (선명함을 높이기 위해 반지름 비율을 0.45로 확대)
    cv2.circle(mask, (w // 2, h // 2), int(min(w, h) * 0.45), 255, -1)
    return mask

def blend_with_object_mask(original_roi, changed_roi, mask, alpha=1.0):
    """
    사물 이진 마스크에 가우시안 블러링을 주어 원본과 변형 ROI를 합성합니다.
    """
    h, w, c = original_roi.shape
    
    # 경계가 너무 뿌옇게 퍼져서 투명해지는 현상을 막기 위해 블러 필터 크기를 최소화하여 선명도 상승
    kernel_size = 3
    
    mask_blur = cv2.GaussianBlur(mask, (kernel_size, kernel_size), 0)
    mask_normalized = mask_blur.astype(np.float32) / 255.0
    mask_normalized = np.expand_dims(mask_normalized, axis=2) * alpha # (H, W, 1)로 변환 및 투명도 반영
    
    # 합성: O * (1 - M) + C * M
    blended = (original_roi.astype(np.float32) * (1.0 - mask_normalized) + 
               changed_roi.astype(np.float32) * mask_normalized)
    
    return blended.astype(np.uint8)

from concurrent.futures import ProcessPoolExecutor

def apply_inpainting_effect(img, x, y, roi_w, roi_h, obj_mask):
    """
    원본 이미지의 특정 물체 영역(obj_mask)을 cv2.inpaint를 사용하여 주변 배경으로 채워 제거합니다.
    """
    h, w = img.shape[:2]
    # 전체 이미지 크기의 이진 마스크 생성
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y:y+roi_h, x:x+roi_w] = obj_mask
    
    # cv2.inpaint 수행 (inpaintRadius는 주변부 픽셀 경계선을 자연스럽게 채우도록 설정)
    inpainted = cv2.inpaint(img, full_mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    return inpainted

def warp_sticker_perspective(sticker, mask):
    """
    스티커와 마스크에 무작위 3D 원근 왜곡(Perspective Warp)을 주어 
    비스듬한 평면에 붙은 듯한 입체감을 시뮬레이션합니다.
    """
    h, w = sticker.shape[:2]
    
    # 원본 네 귀퉁이 좌표
    pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    
    # 무작위 왜곡 오프셋 (너비/높이의 최대 15% 정도 왜곡)
    max_warp_w = int(w * random.uniform(0.06, 0.15))
    max_warp_h = int(h * random.uniform(0.06, 0.15))
    
    # 대상 왜곡 좌표 (안쪽이나 바깥쪽으로 찌그러뜨림)
    pts2 = np.float32([
        [random.randint(0, max_warp_w), random.randint(0, max_warp_h)], # 좌상
        [w - random.randint(0, max_warp_w), random.randint(0, max_warp_h)], # 우상
        [random.randint(0, max_warp_w), h - random.randint(0, max_warp_h)], # 좌하
        [w - random.randint(0, max_warp_w), h - random.randint(0, max_warp_h)]  # 우하
    ])
    
    # 투영 변환 행렬 획득
    matrix = cv2.getPerspectiveTransform(pts1, pts2)
    
    # 변환 적용 (배경은 흰색/검은색 유지)
    warped_sticker = cv2.warpPerspective(sticker, matrix, (w, h), borderValue=(255, 255, 255))
    warped_mask = cv2.warpPerspective(mask, matrix, (w, h), borderValue=0)
    
    return warped_sticker, warped_mask

def blend_sticker_realistically(target_roi, sticker, mask, alpha=1.0):
    """
    마스크 영역에 그림자(Drop Shadow)를 주입하고, 
    원본 이미지의 명암/질감을 약하게 투과시켜 선명하고 선명한 스티커 효과를 냅니다.
    """
    h, w = target_roi.shape[:2]
    
    # 1. 그림자 마스크 생성 (마스크를 오른쪽/아래로 2~3px 밀고 부드럽게 블러)
    shadow_mask = np.zeros((h, w), dtype=np.uint8)
    offset_x = max(1, int(w * 0.05))
    offset_y = max(1, int(h * 0.05))
    
    # 마스크 평행이동
    M = np.float32([[1, 0, offset_x], [0, 1, offset_y]])
    shifted_mask = cv2.warpAffine(mask, M, (w, h), borderValue=0)
    shadow_blur = cv2.GaussianBlur(shifted_mask, (5, 5), 0)
    shadow_normalized = (shadow_blur.astype(np.float32) / 255.0) * 0.35 # 그림자 농도 35%
    shadow_normalized = np.expand_dims(shadow_normalized, axis=2)
    
    # 2. 원본 ROI에 그림자 합성 (원래 배경을 어둡게 만듦)
    roi_shadowed = (target_roi.astype(np.float32) * (1.0 - shadow_normalized)).astype(np.uint8)
    
    # 3. 색상 블렌딩 투과 없이 스티커 원래 색상 그대로 사용
    textured_sticker = sticker.copy()
    
    # 4. 마스크 기반 최종 합성 (가우시안 블러링으로 경계 스무싱)
    mask_blur = cv2.GaussianBlur(mask, (3, 3), 0)
    mask_normalized = mask_blur.astype(np.float32) / 255.0
    mask_normalized = np.expand_dims(mask_normalized, axis=2) * alpha
    
    final_roi = (roi_shadowed.astype(np.float32) * (1.0 - mask_normalized) + 
                 textured_sticker.astype(np.float32) * mask_normalized)
                 
    return final_roi.astype(np.uint8)

def apply_sticker_addition_effect(img, x, y, roi_w, roi_h, alpha=1.0):
    """
    Stickers 폴더 내의 만화 스티커 중 하나를 로드하여 원본 이미지의 (x, y) 위치에 3D 원근 왜곡 및 그림자/텍스처/반투명 블렌딩으로 합성합니다.
    """
    stickers_dir = os.path.join(BASE_DIR, "Images", "Stickers")
    if not os.path.exists(stickers_dir):
        print(f"Stickers 폴더가 없습니다: {stickers_dir}")
        return img.copy()
        
    sticker_files = [f for f in os.listdir(stickers_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not sticker_files:
        print("Stickers 폴더에 스티커 이미지가 없습니다. 빈 이미지 반환합니다.")
        return img.copy()
        
    chosen_sticker_name = random.choice(sticker_files)
    sticker_path = os.path.join(stickers_dir, chosen_sticker_name)
    
    sticker = imread_unicode(sticker_path)
    if sticker is None:
        return img.copy()
        
    # 1. 흰색 배경을 투명 마스크로 분리 (흰색이 아닌 곳을 사물로 인식)
    gray = cv2.cvtColor(sticker, cv2.COLOR_BGR2GRAY)
    _, binary_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    
    # 2. 지정된 ROI 크기에 맞춰 리사이즈
    resized_sticker = cv2.resize(sticker, (roi_w, roi_h), interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(binary_mask, (roi_w, roi_h), interpolation=cv2.INTER_NEAREST)
    
    # 3. 3D 원근 왜곡(Perspective Warp) 적용하여 경사/각도 변환 시뮬레이션
    warped_sticker, warped_mask = warp_sticker_perspective(resized_sticker, resized_mask)
    
    # 4. 합성 영역 추출 및 그림자/명암(Multiply) 블렌딩 적용
    target_roi = img[y:y+roi_h, x:x+roi_w]
    blended = blend_sticker_realistically(target_roi, warped_sticker, warped_mask, alpha)
    
    changed_img = img.copy()
    changed_img[y:y+roi_h, x:x+roi_w] = blended
    
    return changed_img

def find_suitable_position(img, roi_w, roi_h):
    """
    이미지 내부에서 에지 밀도와 중심 에지 포함률을 분석하여, 
    단색 무늬 배경을 피하고 사물의 경계선(Border)이나 디테일이 풍부한 지역 위에 스티커가 붙도록 위치를 선정합니다.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    
    margin_x = int(w * 0.1)
    margin_y = int(h * 0.1)
    
    # 100개의 무작위 후보 영역을 추출하여 에지 픽셀 밀도(디테일/경계 정도)를 세밀하게 분석
    candidates = []
    for _ in range(100):
        x = random.randint(margin_x, w - roi_w - margin_x)
        y = random.randint(margin_y, h - roi_h - margin_y)
        
        roi_edges = edges[y:y+roi_h, x:x+roi_w]
        edge_count = np.sum(roi_edges > 0)
        
        # ROI 중심 영역(가운데 50% 면적)에 에지가 포함되는지 분석 (경계선 부근에 부착 유도)
        cx1, cx2 = roi_w // 4, 3 * roi_w // 4
        cy1, cy2 = roi_h // 4, 3 * roi_h // 4
        center_edges = np.sum(roi_edges[cy1:cy2, cx1:cx2] > 0)
        
        candidates.append((x, y, edge_count, center_edges))
        
    roi_area = roi_w * roi_h
    center_area = (roi_w // 2) * (roi_h // 2)
    
    # 적절한 후보 기준 필터링:
    # 1. 민무늬(단조로운 배경)를 완벽히 피하기 위해 에지 밀도가 최소 8% 이상
    # 2. 물체의 경계선(에지)이 ROI 중심 영역에 확실히 걸쳐 있어 자연스럽게 경계에 매달리도록 유도 (최소 5% 이상)
    suitable_candidates = []
    for x, y, count, center_count in candidates:
        density = count / roi_area
        center_density = center_count / center_area
        if 0.08 <= density <= 0.45 and center_density >= 0.05:
            suitable_candidates.append((x, y))
            
    if suitable_candidates:
        return random.choice(suitable_candidates)
        
    # 적합한 후보군이 없다면 에지 밀도 기준 8%~45% 사이인 후보군 중 랜덤 선택
    fallback_candidates = [
        (x, y) for x, y, count, _ in candidates
        if 0.08 <= (count / roi_area) <= 0.45
    ]
    if fallback_candidates:
        return random.choice(fallback_candidates)
        
    # 그것도 없다면 전체 후보 중 중심 에지 밀도가 가장 높은 후보를 반환하여 단조로운 영역을 완전히 피함
    candidates_sorted = sorted(candidates, key=lambda item: item[3], reverse=True)
    return candidates_sorted[0][0], candidates_sorted[0][1]

def process_single_image(args):
    """
    단일 이미지에 대해 틀린그림찾기 변형 처리를 수행합니다.
    args: (rel_path, rel_path_norm, original_dir, changed_dir, force, existing_coords)
    반환값: (rel_path_norm, coords) 또는 None (처리를 건너뛰거나 실패했을 때)
    """
    rel_path, rel_path_norm, original_dir, changed_dir, force, existing_coords = args
    img_path = os.path.join(original_dir, rel_path)
    changed_path = os.path.join(changed_dir, rel_path)
    
    # force가 아니고 이미 변형된 이미지와 좌표가 있으면 건너뜁니다.
    if not force and os.path.exists(changed_path) and existing_coords:
        return rel_path_norm, existing_coords

    # Changed 폴더 하위에 동일한 서브 디렉터리 구조를 생성합니다.
    os.makedirs(os.path.dirname(changed_path), exist_ok=True)
    
    # 유니코드 지원 함수를 사용해 이미지를 로드합니다.
    img = imread_unicode(img_path)
    if img is None:
        print(f"이미지를 로드할 수 없습니다: {img_path}")
        return None
        
    h, w, c = img.shape
    
    # 실제 화면에 보이는 크기가 고르게 일정하도록 이미지 가로 해상도의 4.0% ~ 5.0% 수준으로 조절 (스티커 왜곡 방지를 위해 정사각 형태 적용, 최소 12px)
    sticker_size = max(12, int(w * random.uniform(0.04, 0.05)))
    roi_w = sticker_size
    roi_h = sticker_size
    
    # 에지 밀도 맵 분석을 통해 최적의 위치(x, y) 탐색
    x, y = find_suitable_position(img, roi_w, roi_h)
    
    # 원래대로 이미지 부착형(Cartoon Sticker) 효과만 사용
    effect_choice = 2
    
    if effect_choice == 0:
        # 원본 ROI 추출 및 마스크 획득
        roi = img[y:y+roi_h, x:x+roi_w]
        mask = get_object_mask(roi)
        # 만화화 또는 색상 변형 효과 적용
        effect_roi = apply_random_effect(roi)
        # 100% 완전 불투명 합성하여 시인성 극대화
        alpha = 1.0
        blended_roi = blend_with_object_mask(roi, effect_roi, mask, alpha=alpha)
        
        changed_img = img.copy()
        changed_img[y:y+roi_h, x:x+roi_w] = blended_roi
        effect_name = "사물 변형 (In-place Modify)"
        
    elif effect_choice == 1:
        # 원본 ROI 추출 및 마스크 획득
        roi = img[y:y+roi_h, x:x+roi_w]
        mask = get_object_mask(roi)
        # 사물 제거 (Inpainting) 효과 적용 - 무조건 100% 완전 제거하여 시인성 보장
        changed_img = apply_inpainting_effect(img, x, y, roi_w, roi_h, mask)
        effect_name = "사물 제거 (Inpaint)"
        
    else:
        # 스티커가 100% 완전 진하게 보이도록 알파값 1.0 설정
        alpha = 1.0
        changed_img = apply_sticker_addition_effect(img, x, y, roi_w, roi_h, alpha=alpha)
        effect_name = "사물 추가 (Cartoon Sticker)"
        
    # 유니코드 지원 함수를 사용해 이미지를 저장합니다.
    success = imwrite_unicode(changed_path, changed_img)
    if not success:
        return None
        
    coords = {
        "x": x,
        "y": y,
        "width": roi_w,
        "height": roi_h
    }
    
    print(f"[{rel_path_norm}] 변형 완료 ({effect_name}) -> x: {coords['x']}, y: {coords['y']}, w: {coords['width']}, h: {coords['height']}")
    return rel_path_norm, coords

def main():
    import sys
    force_all = "--force" in sys.argv
    
    original_dir = os.path.join(BASE_DIR, "Images", "Original")
    changed_dir = os.path.join(BASE_DIR, "Images", "Changed")
    os.makedirs(changed_dir, exist_ok=True)
    
    image_extensions = (".png", ".jpg", ".jpeg")
    
    # os.walk를 활용해 하위 디렉터리 내의 모든 이미지를 수집합니다.
    all_images_rel = []
    for root, dirs, files in os.walk(original_dir):
        for f in files:
            if f.lower().endswith(image_extensions):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, original_dir)
                rel_path_normalized = rel_path.replace(os.sep, '/')
                all_images_rel.append((rel_path, rel_path_normalized))
                
    if not all_images_rel:
        print("Original 폴더에 이미지가 없습니다.")
        return
        
    # 기존 좌표 정보 로드
    coords_path = os.path.join(BASE_DIR, "Images", "diff_coords.json")
    diff_coords = {}
    if os.path.exists(coords_path):
        try:
            with open(coords_path, "r", encoding="utf-8") as f:
                diff_coords = json.load(f)
        except Exception as e:
            print(f"기존 좌표 파일을 읽는 중 오류 발생: {e}. 새로 시작합니다.")
            diff_coords = {}
            
    active_rel_paths = {item[1] for item in all_images_rel}
    
    # 병렬 처리를 위한 작업 리스트 생성
    tasks = []
    for rel_path, rel_path_norm in all_images_rel:
        existing = diff_coords.get(rel_path_norm)
        tasks.append((rel_path, rel_path_norm, original_dir, changed_dir, force_all, existing))
        
    print(f"총 {len(tasks)}개의 이미지 처리 시작 (병렬 처리, force={force_all})...")
    
    new_diff_coords = {}
    processed_count = 0
    
    # CPU 코어 수에 맞추어 프로세스 풀 실행
    with ProcessPoolExecutor() as executor:
        results = executor.map(process_single_image, tasks)
        for res in results:
            if res is not None:
                rel_path_norm, coords = res
                new_diff_coords[rel_path_norm] = coords
                if rel_path_norm not in diff_coords:
                    processed_count += 1
                elif diff_coords[rel_path_norm] != coords:
                    processed_count += 1
                    
    # Original 폴더에 더 이상 존재하지 않는 이미지의 좌표 데이터는 삭제 (동기화)
    new_diff_coords = {k: v for k, v in new_diff_coords.items() if k in active_rel_paths}
    
    # 좌표 정보를 JSON으로 저장
    with open(coords_path, "w", encoding="utf-8") as f:
        json.dump(new_diff_coords, f, indent=4, ensure_ascii=False)
        
    # 로컬 브라우저 CORS 보안 우회용 JS 파일로 저장
    js_coords_path = os.path.join(BASE_DIR, "Images", "diff_coords.js")
    with open(js_coords_path, "w", encoding="utf-8") as f:
        f.write(f"const DIFF_COORDS = {json.dumps(new_diff_coords, indent=4, ensure_ascii=False)};")
        
    if processed_count > 0:
        print(f"이미지 변형 작업 완료! 총 {processed_count}개의 이미지가 새로 처리되었습니다. (전체 {len(new_diff_coords)}개)")
    else:
        print("새로 처리할 이미지가 없습니다. 모든 이미지가 최신 상태입니다. (JS 파일 갱신 완료)")

if __name__ == "__main__":
    main()

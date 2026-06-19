import os
import cv2
import numpy as np
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def imread_unicode(file_path):
    try:
        file_bytes = np.fromfile(file_path, dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"이미지 읽기 중 오류 발생 ({file_path}): {e}")
        return None

def imwrite_unicode(file_path, img):
    try:
        ext = os.path.splitext(file_path)[1]
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

def guided_filter(I, p, r, eps):
    """
    고속 Guided Filter 구현 (OpenCV boxFilter 사용)
    I: guidance image (BGR 이미지)
    p: filtering input (0~1 범위의 float32 마스크)
    r: local window radius
    eps: regularization parameter
    """
    if len(I.shape) == 3:
        I_gray = cv2.cvtColor(I, cv2.COLOR_BGR2GRAY)
    else:
        I_gray = I
        
    I_f = I_gray.astype(np.float32) / 255.0
    p_f = p.astype(np.float32)
    
    mean_I = cv2.boxFilter(I_f, -1, (r, r))
    mean_p = cv2.boxFilter(p_f, -1, (r, r))
    mean_Ip = cv2.boxFilter(I_f * p_f, -1, (r, r))
    
    cov_Ip = mean_Ip - mean_I * mean_p
    
    mean_II = cv2.boxFilter(I_f * I_f, -1, (r, r))
    var_I = mean_II - mean_I * mean_I
    
    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I
    
    mean_a = cv2.boxFilter(a, -1, (r, r))
    mean_b = cv2.boxFilter(b, -1, (r, r))
    
    q = mean_a * I_f + mean_b
    return q

def change_object_color(img, mask):
    """
    마스크 영역에 해당하는 사물의 색상을 선명한 대조색으로 변경합니다.
    mask는 0.0~1.0 사이의 값을 가지는 float32 정밀 마스크입니다 (Guided Filter 결과물).
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    
    # 60~120도 구간 회전으로 확실하게 변경
    hsv_shift = random.choice([random.randint(60, 120), random.randint(-120, -60)])
    
    # 마스크 영역만 색상 변환
    h_new = h.copy()
    s_new = s.copy()
    v_new = v.copy()
    
    # 마스크가 활성화된 영역 (임계값 0.1 이상)
    mask_indices = mask > 0.1
    h_new[mask_indices] = ((h[mask_indices].astype(np.int16) + hsv_shift) % 180).astype(np.uint8)
    
    # 채도 및 명암 강제 보정 (선명하게 보이도록 세팅)
    s_new[mask_indices] = np.clip(s[mask_indices].astype(np.float32) + 120, 150, 255).astype(np.uint8)
    
    # 너무 어둡거나 밝은 색 보정
    v_area = v[mask_indices]
    if len(v_area) > 0:
        if np.mean(v_area) < 70:
            v_new[mask_indices] = np.clip(v_area.astype(np.float32) + 100, 130, 255).astype(np.uint8)
        elif np.mean(v_area) > 180:
            v_new[mask_indices] = np.clip(v_area.astype(np.float32) - 100, 0, 120).astype(np.uint8)
    
    hsv_new = cv2.merge([h_new, s_new, v_new])
    changed_img = cv2.cvtColor(hsv_new, cv2.COLOR_HSV2BGR)
    
    # Guided Filter 마스크 가중치(0.0~1.0)를 사용한 정밀한 알파 블렌딩
    mask_norm = np.expand_dims(mask, axis=2)
    blended = img.astype(np.float32) * (1.0 - mask_norm) + changed_img.astype(np.float32) * mask_norm
    return blended.astype(np.uint8)

def erase_object(img, mask):
    """
    마스크 영역(0.0~1.0 float32)에 해당하는 사물을 인페인팅하여 지웁니다.
    """
    # 0.5 임계치 기준으로 이진화
    binary_mask = (mask > 0.5).astype(np.uint8) * 255
    # 마스크 경계를 살짝 확장하여 잔상이 남지 않고 깔끔하게 지워지도록 처리
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_dilated = cv2.dilate(binary_mask, kernel, iterations=1)
    
    inpainted = cv2.inpaint(img, mask_dilated, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return inpainted

def find_suitable_position_safe(img, roi_w, roi_h, exclusion_mask=None):
    """
    이미지 내부에서 에지 밀도와 중심 에지 포함률을 분석하여,
    단색 무늬 배경을 피하고 사물의 경계선(Border) 위에 스티커/변형이 적용되도록 위치를 선정합니다.
    인물 제외 마스크(exclusion_mask)가 제공되면 해당 영역을 철저히 피합니다.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    
    margin_x = int(w * 0.1)
    margin_y = int(h * 0.1)
    
    candidates = []
    # 150번 무작위 시도하여 인물 영역을 완벽하게 필터링하고 최적 위치 검색
    for _ in range(150):
        x = random.randint(margin_x, w - roi_w - margin_x)
        y = random.randint(margin_y, h - roi_h - margin_y)
        
        # 인물 보호 구역과 겹치는지 검사
        if exclusion_mask is not None:
            roi_ex = exclusion_mask[y:y+roi_h, x:x+roi_w]
            if np.sum(roi_ex > 0) > 0:
                continue
                
        roi_edges = edges[y:y+roi_h, x:x+roi_w]
        edge_count = np.sum(roi_edges > 0)
        
        cx1, cx2 = roi_w // 4, 3 * roi_w // 4
        cy1, cy2 = roi_h // 4, 3 * roi_h // 4
        center_edges = np.sum(roi_edges[cy1:cy2, cx1:cx2] > 0)
        
        candidates.append((x, y, edge_count, center_edges))
        
    if not candidates:
        # 혹시나 인물 제외 구역 때문에 겹치지 않는 구역을 찾지 못했다면 전체 화면에서 인물이 없는 빈 공간 강제 탐색
        for _ in range(100):
            x = random.randint(0, w - roi_w)
            y = random.randint(0, h - roi_h)
            if exclusion_mask is not None:
                roi_ex = exclusion_mask[y:y+roi_h, x:x+roi_w]
                if np.sum(roi_ex > 0) > 0:
                    continue
            return x, y
        # 최악의 경우 (이미지 전체가 인물인 경우 등) 그냥 기본값 반환
        return random.randint(0, w - roi_w), random.randint(0, h - roi_h)
        
    roi_area = roi_w * roi_h
    center_area = (roi_w // 2) * (roi_h // 2)
    
    suitable_candidates = []
    for x, y, count, center_count in candidates:
        density = count / roi_area
        center_density = center_count / center_area
        if 0.08 <= density <= 0.45 and center_density >= 0.05:
            suitable_candidates.append((x, y))
            
    if suitable_candidates:
        return random.choice(suitable_candidates)
        
    fallback_candidates = [
        (x, y) for x, y, count, _ in candidates
        if 0.08 <= (count / roi_area) <= 0.45
    ]
    if fallback_candidates:
        return random.choice(fallback_candidates)
        
    candidates_sorted = sorted(candidates, key=lambda item: item[3], reverse=True)
    return candidates_sorted[0][0], candidates_sorted[0][1]

def process_single_image_ai(args):
    """
    AI 모델 또는 스티커 백업을 사용하여 단일 이미지를 처리합니다.
    """
    rel_path, rel_path_norm, original_dir, changed_dir, force, existing_coords, model = args
    img_path = os.path.join(original_dir, rel_path)
    changed_path = os.path.join(changed_dir, rel_path)
    
    if not force and os.path.exists(changed_path) and existing_coords:
        return rel_path_norm, existing_coords

    os.makedirs(os.path.dirname(changed_path), exist_ok=True)
    img = imread_unicode(img_path)
    if img is None:
        print(f"이미지를 로드할 수 없습니다: {img_path}")
        return None
        
    h, w, c = img.shape
    
    effect_name = ""
    coords = None
    
    # 인물 제외 구역을 저장할 마스크 초기화 (백업 모드에서도 활용하기 위해 밖으로 인출)
    human_exclusion_mask = None
    
    # AI 모델을 사용한 객체 감지 및 세그멘테이션 시도
    if model is not None:
        try:
            results = model(img, verbose=False)
            if len(results) > 0 and results[0].masks is not None:
                masks = results[0].masks.data.cpu().numpy()
                boxes = results[0].boxes.xyxy.cpu().numpy()
                classes = results[0].boxes.cls.cpu().numpy()  # 사물 클래스 ID 가져오기
                
                # 1단계: 사람(클래스 0) 영역에 대한 제외 마스크(human exclusion mask) 구축
                human_mask = np.zeros((h, w), dtype=np.uint8)
                has_human = False
                
                for i in range(len(masks)):
                    if int(classes[i]) == 0:  # person
                        # 세그멘테이션 마스크 리사이즈 및 이진화
                        p_mask = cv2.resize(masks[i], (w, h), interpolation=cv2.INTER_LINEAR)
                        p_mask_bin = (p_mask > 0.3).astype(np.uint8) * 255
                        human_mask = cv2.bitwise_or(human_mask, p_mask_bin)
                        has_human = True
                        
                # 사람 주변 경계를 확장하여 추가적인 안전 마진 확보 (15x15 팽창 연산)
                if has_human:
                    kernel_ex = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
                    human_exclusion_mask = cv2.dilate(human_mask, kernel_ex, iterations=1)
                
                # 2단계: 화면 크기 대비 적당한 사물 크기 필터링 및 사람 영역 배제
                valid_indices = []
                for i in range(len(masks)):
                    # 0번 클래스(person)는 인물 신체/의상 훼손 방지를 위해 제외
                    if int(classes[i]) == 0:
                        continue
                        
                    x1, y1, x2, y2 = boxes[i]
                    box_w = x2 - x1
                    box_h = y2 - y1
                    # 가로/세로 15px 이상이고 전체 화면 너비/높이의 40% 이하 크기의 사물만 선택
                    if 15 <= box_w <= (w * 0.40) and 15 <= box_h <= (h * 0.40):
                        # 사람 제외 구역과 조금이라도 겹치는지 체크
                        if human_exclusion_mask is not None:
                            cand_mask = cv2.resize(masks[i], (w, h), interpolation=cv2.INTER_LINEAR)
                            cand_mask_bin = (cand_mask > 0.3).astype(np.uint8) * 255
                            overlap = cv2.bitwise_and(cand_mask_bin, human_exclusion_mask)
                            if np.sum(overlap > 0) > 0:
                                # 인물 영역과 겹치거나 근처에 있는 사물은 제외
                                continue
                        valid_indices.append(i)
                        
                if valid_indices:
                    chosen_idx = random.choice(valid_indices)
                    
                    # 마스크 이미지를 원본 이미지 해상도로 리사이즈 (선형 보간 사용)
                    obj_mask_resized = cv2.resize(masks[chosen_idx], (w, h), interpolation=cv2.INTER_LINEAR)
                    
                    # Guided Filter를 이용한 고품질 경계선 정밀화
                    obj_mask = guided_filter(img, obj_mask_resized, r=5, eps=0.01)
                    obj_mask = np.clip(obj_mask, 0.0, 1.0)
                    
                    x1, y1, x2, y2 = boxes[chosen_idx]
                    box_w = int(x2 - x1)
                    box_h = int(y2 - y1)
                    
                    # 뭉개짐(번짐)을 최소화하기 위해 크기가 가로/세로 8% 이하인 사물일 때 사물 제거(Inpaint) 허용 (Guided Filter 적용으로 화질 개선)
                    is_small = (box_w <= w * 0.08) and (box_h <= h * 0.08)
                    
                    if is_small:
                        effect_choice = random.choice([0, 1])
                    else:
                        effect_choice = 0
                        
                    if effect_choice == 0:
                        changed_img = change_object_color(img, obj_mask)
                        effect_name = f"AI 사물 색상 변경"
                    else:
                        changed_img = erase_object(img, obj_mask)
                        effect_name = f"AI 사물 제거"
                        
                    coords = {
                        "x": int(x1),
                        "y": int(y1),
                        "width": box_w,
                        "height": box_h
                    }
        except Exception as e:
            print(f"AI 분석 중 오류 발생, 스티커 백업 모드로 전환: {e}")
            
    # AI로 사물 감지에 실패했거나 모델이 없을 때 -> 기존의 전통 CV 방식으로 백업 처리
    if coords is None:
        # Stickers 폴더 내 스티커 추가 효과 임포트 및 전통 방식 유틸 임포트
        from generate_difference import (
            apply_sticker_addition_effect,
            apply_random_effect,
            get_object_mask,
            blend_with_object_mask,
            apply_inpainting_effect
        )
        
        # 화면에 맞게 일정하게 화면 기준 정형화된 사이즈로 조절 (4% ~ 5%, 최소 12px)
        sticker_size = max(12, int(w * random.uniform(0.04, 0.05)))
        roi_w = sticker_size
        roi_h = sticker_size
        
        # 사람 영역을 우회하는 안전한 영역 선정
        x, y = find_suitable_position_safe(img, roi_w, roi_h, human_exclusion_mask)
        
        # 백업 모드에서도 다양성을 위해 스티커 추가, 사물 제거(인페인트), 사물 변형(색상/카툰) 중 랜덤 선택
        effect_choice = random.choice([0, 1, 2])
        
        if effect_choice == 0:
            changed_img = apply_sticker_addition_effect(img, x, y, roi_w, roi_h, alpha=1.0)
            effect_name = "스티커 추가 (백업)"
        elif effect_choice == 1:
            roi = img[y:y+roi_h, x:x+roi_w]
            local_mask = get_object_mask(roi)
            changed_img = apply_inpainting_effect(img, x, y, roi_w, roi_h, local_mask)
            effect_name = "사물 제거 (백업)"
        else:
            roi = img[y:y+roi_h, x:x+roi_w]
            local_mask = get_object_mask(roi)
            effect_roi = apply_random_effect(roi)
            blended_roi = blend_with_object_mask(roi, effect_roi, local_mask, alpha=1.0)
            changed_img = img.copy()
            changed_img[y:y+roi_h, x:x+roi_w] = blended_roi
            effect_name = "사물 변형 (백업)"
            
        coords = {
            "x": x,
            "y": y,
            "width": roi_w,
            "height": roi_h
        }
        
    success = imwrite_unicode(changed_path, changed_img)
    if not success:
        return None
        
    print(f"[{rel_path_norm}] {effect_name} 완료 -> x: {coords['x']}, y: {coords['y']}, w: {coords['width']}, h: {coords['height']}")
    return rel_path_norm, coords

def main():
    import sys
    force_all = "--force" in sys.argv
    
    # YOLOv8-seg 로드 시도
    model = None
    try:
        from ultralytics import YOLO
        # 가장 가볍고 속도가 빠른 7MB 크기의 nano 모델 사용
        # 로컬 폴더에 모델 파일이 없으면 인터넷에서 자동 다운로드됩니다.
        model_path = os.path.join(BASE_DIR, "yolov8n-seg.pt")
        model = YOLO(model_path)
        print("YOLOv8-seg AI 모델이 성공적으로 로드되었습니다.")
    except ImportError:
        print("ultralytics 라이브러리가 설치되지 않았습니다. 스티커 백업 모드로만 작동합니다.")
        print("설치 방법: pip install ultralytics torch torchvision")
    except Exception as e:
        print(f"AI 모델 로드 실패 (스티커 백업 모드 실행): {e}")

    original_dir = os.path.join(BASE_DIR, "Images", "Original")
    changed_dir = os.path.join(BASE_DIR, "Images", "Changed")
    os.makedirs(changed_dir, exist_ok=True)
    
    image_extensions = (".png", ".jpg", ".jpeg")
    
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
    
    # AI 모델 추론은 ThreadPool로 병렬도 제어
    tasks = []
    for rel_path, rel_path_norm in all_images_rel:
        existing = diff_coords.get(rel_path_norm)
        tasks.append((rel_path, rel_path_norm, original_dir, changed_dir, force_all, existing, model))
        
    print(f"총 {len(tasks)}개의 이미지 처리 시작 (AI 탐색 및 변형, force={force_all})...")
    
    new_diff_coords = {}
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(process_single_image_ai, tasks)
        for res in results:
            if res is not None:
                rel_path_norm, coords = res
                new_diff_coords[rel_path_norm] = coords
                if rel_path_norm not in diff_coords:
                    processed_count += 1
                elif diff_coords[rel_path_norm] != coords:
                    processed_count += 1
                    
    new_diff_coords = {k: v for k, v in new_diff_coords.items() if k in active_rel_paths}
    
    with open(coords_path, "w", encoding="utf-8") as f:
        json.dump(new_diff_coords, f, indent=4, ensure_ascii=False)
        
    js_coords_path = os.path.join(BASE_DIR, "Images", "diff_coords.js")
    with open(js_coords_path, "w", encoding="utf-8") as f:
        f.write(f"const DIFF_COORDS = {json.dumps(new_diff_coords, indent=4, ensure_ascii=False)};")
        
    if processed_count > 0:
        print(f"AI 이미지 변형 완료! 총 {processed_count}개의 이미지가 새로 처리되었습니다. (전체 {len(new_diff_coords)}개)")
    else:
        print("새로 처리할 이미지가 없습니다. 모든 이미지가 최신 상태입니다. (JS 파일 갱신 완료)")

if __name__ == "__main__":
    main()

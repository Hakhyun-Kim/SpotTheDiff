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

def change_object_color(img, mask):
    """
    마스크 영역에 해당하는 사물의 색상을 선명한 대조색으로 변경합니다.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    
    # 60~120도 구간 회전으로 확실하게 변경
    hsv_shift = random.choice([random.randint(60, 120), random.randint(-120, -60)])
    
    # 마스크 영역만 색상 변환
    h_new = h.copy()
    s_new = s.copy()
    v_new = v.copy()
    
    h_new[mask > 0] = ((h[mask > 0].astype(np.int16) + hsv_shift) % 180).astype(np.uint8)
    
    # 채도 및 명암 강제 보정 (선명하게 보이도록 세팅)
    s_new[mask > 0] = np.clip(s[mask > 0].astype(np.float32) + 120, 150, 255).astype(np.uint8)
    
    # 너무 어둡거나 밝은 색 보정
    v_area = v[mask > 0]
    if np.mean(v_area) < 70:
        v_new[mask > 0] = np.clip(v_area.astype(np.float32) + 100, 130, 255).astype(np.uint8)
    elif np.mean(v_area) > 180:
        v_new[mask > 0] = np.clip(v_area.astype(np.float32) - 100, 0, 120).astype(np.uint8)
    
    hsv_new = cv2.merge([h_new, s_new, v_new])
    changed_img = cv2.cvtColor(hsv_new, cv2.COLOR_HSV2BGR)
    
    # 마스크 경계를 아주 미세한 가우시안 블러(3x3)로 자연스럽고 또렷하게 합성
    mask_blur = cv2.GaussianBlur((mask * 255).astype(np.uint8), (3, 3), 0)
    mask_norm = mask_blur.astype(np.float32) / 255.0
    mask_norm = np.expand_dims(mask_norm, axis=2)
    
    blended = img.astype(np.float32) * (1.0 - mask_norm) + changed_img.astype(np.float32) * mask_norm
    return blended.astype(np.uint8)

def erase_object(img, mask):
    """
    마스크 영역에 해당하는 사물을 인페인팅하여 지웁니다.
    """
    # 마스크 경계를 살짝 확장하여 잔상이 남지 않고 깔끔하게 지워지도록 처리
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_dilated = cv2.dilate((mask * 255).astype(np.uint8), kernel, iterations=1)
    
    inpainted = cv2.inpaint(img, mask_dilated, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    return inpainted

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
    
    # AI 모델을 사용한 객체 감지 및 세그멘테이션 시도
    if model is not None:
        try:
            results = model(img, verbose=False)
            if len(results) > 0 and results[0].masks is not None:
                masks = results[0].masks.data.cpu().numpy()
                boxes = results[0].boxes.xyxy.cpu().numpy()
                
                # 화면 크기 대비 적당한 사물 크기 필터링 (가로/세로 35px 이상이고 전체 화면 너비/높이의 15% 이하 크기의 사물만 선택)
                valid_indices = []
                for i in range(len(masks)):
                    x1, y1, x2, y2 = boxes[i]
                    box_w = x2 - x1
                    box_h = y2 - y1
                    if 35 <= box_w <= (w * 0.15) and 35 <= box_h <= (h * 0.15):
                        valid_indices.append(i)
                        
                if valid_indices:
                    chosen_idx = random.choice(valid_indices)
                    # 마스크 이미지를 원본 이미지 해상도로 리사이즈
                    obj_mask = cv2.resize(masks[chosen_idx], (w, h), interpolation=cv2.INTER_NEAREST)
                    
                    x1, y1, x2, y2 = boxes[chosen_idx]
                    box_w = int(x2 - x1)
                    box_h = int(y2 - y1)
                    
                    # 50% 확률로 사물 색상 변경 또는 사물 제거(Inpaint) 적용
                    effect_choice = random.choice([0, 1])
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
            
    # AI로 사물 감지에 실패했거나 모델이 없을 때 -> 기존의 스티커 방식으로 백업 처리
    if coords is None:
        # Stickers 폴더 내 스티커 추가 효과 임포트
        from generate_difference import find_suitable_position, apply_sticker_addition_effect
        
        # 화면에 맞게 일정하게 화면 기준 정형화된 사이즈로 조절 (4% ~ 5%, 최소 12px)
        sticker_size = max(12, int(w * random.uniform(0.04, 0.05)))
        roi_w = sticker_size
        roi_h = sticker_size
        
        x, y = find_suitable_position(img, roi_w, roi_h)
        changed_img = apply_sticker_addition_effect(img, x, y, roi_w, roi_h, alpha=1.0)
        effect_name = "스티커 추가 (백업)"
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

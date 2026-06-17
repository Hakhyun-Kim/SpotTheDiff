import os
import json
from flask import Flask, request, jsonify, send_from_directory
from generate_difference import process_single_image

app = Flask(__name__, static_folder='.', static_url_path='')

ORIGINAL_DIR = r"d:\FindDIfference\Images\Original"
CHANGED_DIR = r"d:\FindDIfference\Images\Changed"
COORDS_PATH = os.path.join(r"d:\FindDIfference\Images", "diff_coords.json")
JS_COORDS_PATH = os.path.join(r"d:\FindDIfference\Images", "diff_coords.js")

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/regenerate', methods=['POST'])
def regenerate_image():
    data = request.get_json()
    if not data or 'path' not in data:
        return jsonify({"success": False, "error": "Invalid request parameters"}), 400
    
    rel_path_norm = data['path']
    # 윈도우 OS 경로 형태로 호환되게 변환
    rel_path = rel_path_norm.replace('/', os.sep)
    
    # process_single_image 호출 파라미터 구성
    # args: (rel_path, rel_path_norm, original_dir, changed_dir, force, existing_coords)
    args = (rel_path, rel_path_norm, ORIGINAL_DIR, CHANGED_DIR, True, None)
    
    try:
        result = process_single_image(args)
        if result is None:
            return jsonify({"success": False, "error": "Image generation failed"}), 500
        
        _, coords = result
        
        # diff_coords.json 로드하여 업데이트
        diff_coords = {}
        if os.path.exists(COORDS_PATH):
            try:
                with open(COORDS_PATH, "r", encoding="utf-8") as f:
                    diff_coords = json.load(f)
            except Exception as e:
                print(f"Error loading JSON coords: {e}")
        
        # 새로운 좌표 적용
        diff_coords[rel_path_norm] = coords
        
        # 다시 저장
        with open(COORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(diff_coords, f, indent=4, ensure_ascii=False)
            
        # js 파일도 갱신
        with open(JS_COORDS_PATH, "w", encoding="utf-8") as f:
            f.write(f"const DIFF_COORDS = {json.dumps(diff_coords, indent=4, ensure_ascii=False)};")
            
        return jsonify({
            "success": True,
            "coords": coords
        })
        
    except Exception as e:
        print(f"Error regenerating image: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # 로컬 네트워크에서도 접속 가능하도록 0.0.0.0 포트 6001로 실행
    app.run(host='0.0.0.0', port=6001, debug=True)

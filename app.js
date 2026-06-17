/* ==========================================================================
   PREMIUM SPOT THE DIFFERENCE - GAME LOGIC
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // ----------------------------------------------------------------------
    // STATE VARIABLES
    // ----------------------------------------------------------------------
    let themes = {};            // 테마별 스테이지 정보 맵
    let playlist = [];          // 현재 진행 중인 테마의 스테이지 목록
    let stageIndex = 0;         // 현재 스테이지 인덱스
    let lives = 5;              // 남은 하트 수 (기본 5개)
    let hintsLeft = 3;          // 남은 힌트 수 (기본 3개)
    let gameActive = false;     // 클릭 판정 활성화 여부
    let timerInterval = null;   // 타이머 인터벌 객체
    let elapsedSeconds = 0;     // 경과 시간(초)
    let currentImageSize = {    // 현재 이미지 원본 크기
        naturalWidth: 1,
        naturalHeight: 1
    };

    // ----------------------------------------------------------------------
    // HTML ELEMENTS
    // ----------------------------------------------------------------------
    const dashboardScreen = document.getElementById('dashboard-screen');
    const gameScreen = document.getElementById('game-screen');
    const themeCardsContainer = document.getElementById('theme-cards-container');
    
    // Status Bar Elements
    const btnBackToLobby = document.getElementById('btn-back-to-lobby');
    const currentStageNum = document.getElementById('current-stage-num');
    const gameTimer = document.getElementById('game-timer');
    const heartContainer = document.getElementById('heart-container');
    
    // Playfield Elements
    const gameApp = document.getElementById('game-app');
    const imgOriginal = document.getElementById('img-original');
    const imgChanged = document.getElementById('img-changed');
    const overlayOriginal = document.getElementById('overlay-original');
    const overlayChanged = document.getElementById('overlay-changed');
    const reticleOriginal = document.getElementById('reticle-original');
    const reticleChanged = document.getElementById('reticle-changed');
    
    // Bottom Controls
    const gameHint = document.getElementById('game-hint');
    const btnGameHint = document.getElementById('btn-game-hint');
    const hintCount = document.getElementById('hint-count');
    const btnNextStage = document.getElementById('btn-next-stage');
    
    // Modals
    const modalClear = document.getElementById('modal-clear');
    const modalGameOver = document.getElementById('modal-gameover');
    
    // Clear Modal Stats
    const modalClearTitle = document.getElementById('modal-clear-title');
    const statTotalTime = document.getElementById('stat-total-time');
    const statRemainingLives = document.getElementById('stat-remaining-lives');
    
    // Modal Action Buttons
    const btnModalRetry = document.getElementById('btn-modal-retry');
    const btnModalLobby = document.getElementById('btn-modal-lobby');
    const btnModalRetryFailed = document.getElementById('btn-modal-retry-failed');
    const btnModalLobbyFailed = document.getElementById('btn-modal-lobby-failed');

    // ----------------------------------------------------------------------
    // 1. DATA PARSING & INITIALIZATION
    // ----------------------------------------------------------------------
    function initData() {
        if (typeof DIFF_COORDS === 'undefined') {
            console.error("좌표 데이터(DIFF_COORDS)를 찾을 수 없습니다. diff_coords.js 파일이 올바르게 로드되었는지 확인하세요.");
            themeCardsContainer.innerHTML = `<p class="error-msg">좌표 데이터를 로드할 수 없습니다. 스크립트를 먼저 실행해 주세요.</p>`;
            return;
        }

        // 테마명 자동 추출 및 분류 (예: 'stage1/dessert.png' -> 테마 'stage1', 파일 'dessert.png')
        themes = {};
        for (const path in DIFF_COORDS) {
            const parts = path.split('/');
            let themeName = 'General';
            if (parts.length > 1) {
                themeName = parts[0];
            }
            
            if (!themes[themeName]) {
                themes[themeName] = [];
            }
            themes[themeName].push({
                path: path,
                coords: DIFF_COORDS[path]
            });
        }

        renderThemeCards();
    }

    // 테마별 어울리는 아이콘 매핑
    function getThemeIcon(themeName) {
        const lowerName = themeName.toLowerCase();
        if (lowerName.includes('stage1')) return '🍰'; // 디저트/숲 등
        if (lowerName.includes('stage2')) return '🖼️'; // 인테리어/방
        if (lowerName.includes('album') || lowerName.includes('앨범')) return '📸';
        return '🎮';
    }

    // 테마별 친절한 한글 이름 매핑
    function getThemeKoreanName(themeName) {
        const lowerName = themeName.toLowerCase();
        if (lowerName === 'stage1') return '테마 1: 신비와 미식';
        if (lowerName === 'stage2') return '테마 2: 아늑한 일상';
        if (lowerName === '앨범') return '테마 3: 추억의 사진첩';
        return themeName;
    }

    function renderThemeCards() {
        themeCardsContainer.innerHTML = '';
        
        for (const themeName in themes) {
            const stageCount = themes[themeName].length;
            const icon = getThemeIcon(themeName);
            const koreanName = getThemeKoreanName(themeName);
            
            const card = document.createElement('div');
            card.className = 'theme-card';
            card.innerHTML = `
                <div class="theme-icon">${icon}</div>
                <div class="theme-title">${koreanName}</div>
                <div class="theme-meta">총 ${stageCount}개의 스테이지</div>
                <div class="theme-badge">준비 완료</div>
            `;
            
            card.addEventListener('click', () => {
                startTheme(themeName);
            });
            
            themeCardsContainer.appendChild(card);
        }
    }

    // ----------------------------------------------------------------------
    // 2. GAME CONTROL FLOW
    // ----------------------------------------------------------------------
    function startTheme(themeName) {
        // 해당 테마의 스테이지 복제 후 랜덤 셔플
        const originalList = themes[themeName];
        playlist = [...originalList].sort(() => Math.random() - 0.5);
        
        // 만약 스테이지 개수가 너무 많다면 최대 5~10개 정도로 잘라 한 게임의 피로도를 덜 수 있습니다.
        // 여기서는 유연하게 모든 카드를 보여주되 최대 10개로 제한하도록 하겠습니다. (앨범에 160개 넘는 카드가 있으므로)
        const maxStagesPerGame = 10;
        if (playlist.length > maxStagesPerGame) {
            playlist = playlist.slice(0, maxStagesPerGame);
        }

        stageIndex = 0;
        lives = 5;
        hintsLeft = 3;
        elapsedSeconds = 0;
        
        // 힌트 버튼 활성화 상태 및 텍스트 리셋
        btnGameHint.disabled = false;
        hintCount.textContent = "3/3";
        
        // 화면 스위칭
        dashboardScreen.classList.add('hidden');
        gameScreen.classList.remove('hidden');
        
        // 타이머 시작
        startTimer();
        
        // 첫 스테이지 로드
        loadStage();
    }

    function loadStage() {
        gameActive = false;
        btnNextStage.classList.add('hidden');
        gameHint.textContent = "두 이미지에서 다른 곳 한 군데를 마우스로 클릭해 보세요!";
        gameHint.className = "hint-message";
        
        // 힌트 버튼 활성화 상태 제어 (남은 개수에 따라)
        btnGameHint.disabled = (hintsLeft <= 0);
        hintCount.textContent = `${hintsLeft}/3`;
        
        // 기존 링/실패 X 표시 클리어
        clearEffects();
        
        const stage = playlist[stageIndex];
        currentStageNum.textContent = `${stageIndex + 1}/${playlist.length}`;
        
        // 하트(라이프) UI 업데이트
        updateHeartsUI();

        // 이미지 소스 매칭
        // 캐시 방지를 방지할 필요는 없지만 깔끔하게 경로 렌더링
        imgOriginal.src = `Images/Original/${stage.path}`;
        imgChanged.src = `Images/Changed/${stage.path}`;

        // 이미지 둘 다 로드 완료 시 판정 영역 및 비율 갱신
        let originalLoaded = false;
        let changedLoaded = false;

        function checkAllLoaded() {
            if (originalLoaded && changedLoaded) {
                // 이미지의 natural 해상도 저장
                currentImageSize.naturalWidth = imgOriginal.naturalWidth;
                currentImageSize.naturalHeight = imgOriginal.naturalHeight;
                gameActive = true;
            }
        }

        imgOriginal.onload = () => {
            originalLoaded = true;
            checkAllLoaded();
        };
        imgChanged.onload = () => {
            changedLoaded = true;
            checkAllLoaded();
        };
    }

    // ----------------------------------------------------------------------
    // 3. INTERACTIVE RETICLE (SYNC CROSSHAIR)
    // ----------------------------------------------------------------------
    function syncPointer(event, activeOverlay, targetReticle, partnerReticle) {
        const rect = activeOverlay.getBoundingClientRect();
        // 이미지 크기에 대한 퍼센트 비율 좌표 구함
        const xPct = ((event.clientX - rect.left) / rect.width) * 100;
        const yPct = ((event.clientY - rect.top) / rect.height) * 100;
        
        // 0% ~ 100% 바운더리 클램핑
        const clampedX = Math.max(0, Math.min(100, xPct));
        const clampedY = Math.max(0, Math.min(100, yPct));
        
        // 양쪽 십자선 동기화 배치
        targetReticle.style.left = `${clampedX}%`;
        targetReticle.style.top = `${clampedY}%`;
        partnerReticle.style.left = `${clampedX}%`;
        partnerReticle.style.top = `${clampedY}%`;
    }

    overlayOriginal.addEventListener('mousemove', (e) => {
        if (!gameActive) return;
        syncPointer(e, overlayOriginal, reticleOriginal, reticleChanged);
    });

    overlayChanged.addEventListener('mousemove', (e) => {
        if (!gameActive) return;
        syncPointer(e, overlayChanged, reticleChanged, reticleOriginal);
    });

    // ----------------------------------------------------------------------
    // 4. CLICK DETECTION & HIT LOGIC
    // ----------------------------------------------------------------------
    function handleOverlayClick(event, activeOverlay) {
        if (!gameActive) return;

        const rect = activeOverlay.getBoundingClientRect();
        const xPct = (event.clientX - rect.left) / rect.width;
        const yPct = (event.clientY - rect.top) / rect.height;
        
        // 클릭 비율 좌표를 원본 해상도 기준으로 환산
        const clickX = xPct * currentImageSize.naturalWidth;
        const clickY = yPct * currentImageSize.naturalHeight;

        // 현재 스테이지 정답 영역 정보 가져오기
        const target = playlist[stageIndex];
        const box = target.coords;

        // 클릭 편의성을 위해 판정 영역 사방에 15px 보정 버퍼 부여
        const buffer = 15;
        const isHit = (
            clickX >= box.x - buffer &&
            clickX <= box.x + box.width + buffer &&
            clickY >= box.y - buffer &&
            clickY <= box.y + box.height + buffer
        );

        if (isHit) {
            handleHit(box);
        } else {
            handleMiss(xPct, yPct);
        }
    }

    overlayOriginal.addEventListener('click', (e) => handleOverlayClick(e, overlayOriginal));
    overlayChanged.addEventListener('click', (e) => handleOverlayClick(e, overlayChanged));

    // 정답 처리 (Hit)
    function handleHit(box) {
        gameActive = false;
        
        // 네온 링 이펙트 드로잉 (원본 해상도 대비 백분율 크기)
        const cxPct = ((box.x + box.width / 2) / currentImageSize.naturalWidth) * 100;
        const cyPct = ((box.y + box.height / 2) / currentImageSize.naturalHeight) * 100;
        const ringSizePct = ((Math.max(box.width, box.height) + 30) / currentImageSize.naturalWidth) * 100;

        createNeonRing(cxPct, cyPct, ringSizePct);

        // 파티클 방출 (Canvas Confetti)
        triggerConfetti();

        // 힌트 상태 갱신
        gameHint.textContent = "성공! 잠시 후 다음 이미지로 자동 이동합니다.";
        gameHint.className = "hint-message success";

        // 1.2초 후 자동으로 다음 스테이지로 스위칭
        setTimeout(() => {
            if (stageIndex < playlist.length - 1) {
                stageIndex++;
                loadStage();
            } else {
                handleGameClear();
            }
        }, 1200);
    }

    // 오답 처리 (Miss)
    function handleMiss(xPct, yPct) {
        // 클릭한 위치에 붉은색 X 표시 일시적 생성
        createFailX(xPct * 100, yPct * 100);
        
        // 화면 흔들림 효과 부여
        gameApp.classList.add('shake');
        setTimeout(() => {
            gameApp.classList.remove('shake');
        }, 500);

        // 라이프 차감
        lives--;
        updateHeartsUI();

        if (lives <= 0) {
            handleGameOver();
        }
    }

    // ----------------------------------------------------------------------
    // 5. EFFECT DRAWING HELPERS
    // ----------------------------------------------------------------------
    function createNeonRing(xPct, yPct, sizePct) {
        // 최소 크기 제한 (너무 작아 보이지 않도록)
        const size = Math.max(5, sizePct);
        
        const ringOriginal = document.createElement('div');
        ringOriginal.className = 'success-ring';
        ringOriginal.style.left = `${xPct}%`;
        ringOriginal.style.top = `${yPct}%`;
        ringOriginal.style.width = `${size}%`;
        ringOriginal.style.paddingTop = `${size}%`; // 1:1 종횡비 유지용 꼼수

        const ringChanged = ringOriginal.cloneNode(true);
        
        overlayOriginal.appendChild(ringOriginal);
        overlayChanged.appendChild(ringChanged);
    }

    function createFailX(xPct, yPct) {
        const failX = document.createElement('div');
        failX.className = 'fail-x';
        failX.textContent = '❌';
        failX.style.left = `${xPct}%`;
        failX.style.top = `${yPct}%`;
        
        // 클릭한 이미지 측 오버레이 레이어에 표시
        overlayOriginal.appendChild(failX);
        
        // 복제본 생성하여 반대편에도 동일한 비율 좌표에 일시 표시
        const failXPartner = failX.cloneNode(true);
        overlayChanged.appendChild(failXPartner);

        setTimeout(() => {
            failX.remove();
            failXPartner.remove();
        }, 500);
    }

    function clearEffects() {
        // 기존 링 및 X 마크 삭제
        const rings = document.querySelectorAll('.success-ring');
        rings.forEach(r => r.remove());
        const fails = document.querySelectorAll('.fail-x');
        fails.forEach(f => f.remove());
        const hintRings = document.querySelectorAll('.hint-ring');
        hintRings.forEach(h => h.remove());
    }

    // 힌트 기능 구현
    function useHint() {
        if (!gameActive || hintsLeft <= 0) return;

        hintsLeft--;
        hintCount.textContent = `${hintsLeft}/3`;
        
        if (hintsLeft === 0) {
            btnGameHint.disabled = true;
        }

        const target = playlist[stageIndex];
        const box = target.coords;

        // 힌트 가이드 서클 위치 계산 (원본 해상도 대비 백분율)
        const cxPct = ((box.x + box.width / 2) / currentImageSize.naturalWidth) * 100;
        const cyPct = ((box.y + box.height / 2) / currentImageSize.naturalHeight) * 100;
        
        // 링의 크기를 정답 박스 크기보다 살짝 넉넉하게 잡음
        const ringSizePct = ((Math.max(box.width, box.height) + 50) / currentImageSize.naturalWidth) * 100;
        const size = Math.max(8, ringSizePct);

        // 힌트 서클 요소 생성 및 부착
        const ringOriginal = document.createElement('div');
        ringOriginal.className = 'hint-ring';
        ringOriginal.style.left = `${cxPct}%`;
        ringOriginal.style.top = `${cyPct}%`;
        ringOriginal.style.width = `${size}%`;
        ringOriginal.style.paddingTop = `${size}%`;

        const ringChanged = ringOriginal.cloneNode(true);

        overlayOriginal.appendChild(ringOriginal);
        overlayChanged.appendChild(ringChanged);

        // 1.5초 후 힌트 링을 페이드아웃하며 삭제
        setTimeout(() => {
            ringOriginal.style.transition = 'opacity 0.4s ease';
            ringChanged.style.transition = 'opacity 0.4s ease';
            ringOriginal.style.opacity = '0';
            ringChanged.style.opacity = '0';
            setTimeout(() => {
                ringOriginal.remove();
                ringChanged.remove();
            }, 400);
        }, 1500);
    }

    function triggerConfetti() {
        // 왼쪽 하단 구석에서
        confetti({
            particleCount: 40,
            angle: 60,
            spread: 55,
            origin: { x: 0.1, y: 0.8 }
        });
        // 오른쪽 하단 구석에서
        confetti({
            particleCount: 40,
            angle: 120,
            spread: 55,
            origin: { x: 0.9, y: 0.8 }
        });
    }

    // ----------------------------------------------------------------------
    // 6. UI UPDATING & STATS
    // ----------------------------------------------------------------------
    function updateHeartsUI() {
        heartContainer.innerHTML = '';
        const maxLives = 5;
        for (let i = 0; i < maxLives; i++) {
            const heart = document.createElement('span');
            heart.className = 'heart-icon' + (i >= lives ? ' lost' : '');
            heart.textContent = '♥';
            heart.style.transitionDelay = `${i * 0.05}s`;
            heartContainer.appendChild(heart);
        }
    }

    // ----------------------------------------------------------------------
    // 7. TIMER LOGIC
    // ----------------------------------------------------------------------
    function startTimer() {
        clearInterval(timerInterval);
        gameTimer.textContent = "00:00";
        timerInterval = setInterval(() => {
            elapsedSeconds++;
            const minutes = Math.floor(elapsedSeconds / 60);
            const seconds = elapsedSeconds % 60;
            
            const mm = minutes.toString().padStart(2, '0');
            const ss = seconds.toString().padStart(2, '0');
            gameTimer.textContent = `${mm}:${ss}`;
        }, 1000);
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    // ----------------------------------------------------------------------
    // 8. NEXT STAGE & END GAMES
    // ----------------------------------------------------------------------
    btnNextStage.addEventListener('click', () => {
        if (stageIndex < playlist.length - 1) {
            stageIndex++;
            loadStage();
        } else {
            handleGameClear();
        }
    });

    function handleGameClear() {
        stopTimer();
        gameActive = false;
        
        // 완주 성공 통계 모달 세팅
        const minutes = Math.floor(elapsedSeconds / 60);
        const seconds = elapsedSeconds % 60;
        const mm = minutes.toString().padStart(2, '0');
        const ss = seconds.toString().padStart(2, '0');
        
        statTotalTime.textContent = `${mm}:${ss}`;
        
        let heartsStr = '';
        for (let i = 0; i < lives; i++) heartsStr += '♥';
        statRemainingLives.textContent = heartsStr || '없음';
        statRemainingLives.style.color = 'var(--danger)';

        modalClear.classList.remove('hidden');
        
        // 최종 팡파레 지속 발사
        let end = Date.now() + (1.5 * 1000);
        (function frame() {
            confetti({
                particleCount: 3,
                angle: 60,
                spread: 55,
                origin: { x: 0 },
                colors: ['#5856d6', '#00e676', '#ff2d55']
            });
            confetti({
                particleCount: 3,
                angle: 120,
                spread: 55,
                origin: { x: 1 },
                colors: ['#5856d6', '#00e676', '#ff2d55']
            });
            if (Date.now() < end) {
                requestAnimationFrame(frame);
            }
        }());
    }

    function handleGameOver() {
        stopTimer();
        gameActive = false;
        modalGameOver.classList.remove('hidden');
    }

    // ----------------------------------------------------------------------
    // 9. LOBBY NAVIGATION & ACTIONS
    // ----------------------------------------------------------------------
    function returnToLobby() {
        stopTimer();
        gameActive = false;
        clearEffects();
        
        // 모달창 다 닫기
        modalClear.classList.add('hidden');
        modalGameOver.classList.add('hidden');
        
        // 게임화면 닫고 로비 활성화
        gameScreen.classList.add('hidden');
        dashboardScreen.classList.remove('hidden');
    }

    btnBackToLobby.addEventListener('click', returnToLobby);
    btnModalLobby.addEventListener('click', returnToLobby);
    btnModalLobbyFailed.addEventListener('click', returnToLobby);
    btnGameHint.addEventListener('click', useHint);

    // 다시 시도
    function restartCurrentTheme() {
        modalClear.classList.add('hidden');
        modalGameOver.classList.add('hidden');
        
        // 로드된 플레이리스트 그대로 셔플하여 첫 스테이지부터 다시 구동
        playlist.sort(() => Math.random() - 0.5);
        stageIndex = 0;
        lives = 5;
        hintsLeft = 3;
        elapsedSeconds = 0;
        
        btnGameHint.disabled = false;
        hintCount.textContent = "3/3";
        
        startTimer();
        loadStage();
    }

    btnModalRetry.addEventListener('click', restartCurrentTheme);
    btnModalRetryFailed.addEventListener('click', restartCurrentTheme);

    // ----------------------------------------------------------------------
    // APP START
    // ----------------------------------------------------------------------
    initData();
});

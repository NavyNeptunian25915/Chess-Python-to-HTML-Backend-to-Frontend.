const API_BASE = 'http://localhost:6400/api';

// Piece Unicode symbols
const PIECES = {
    'P': '♟', 'N': '♞', 'B': '♝', 'R': '♜', 'Q': '♛', 'K': '♚',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
};

// Grade colors mapping
const GRADE_COLORS = {
    'Sigma': '#00FFFF',
    'Chad': '#00FF80',
    'Good': '#00FF00',
    'Okay': '#80FF00',
    'Strange': '#FFFF00',
    'Bad': '#FF8000',
    'Clown': '#FF0000'
};

// Game state
let currentFEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
let moveHistory = [];
let engineReady = false;
let draggedFrom = null;
let draggedPiece = null;

// Move grades tracker
// Per-player move grade tracking
let playerGradeDistribution = {
    white: { Sigma: 0, Chad: 0, Good: 0, Okay: 0, Strange: 0, Bad: 0, Clown: 0 },
    black: { Sigma: 0, Chad: 0, Good: 0, Okay: 0, Strange: 0, Bad: 0, Clown: 0 }
};

// DOM Elements
const chessboard = document.getElementById('chessboard');
const backButton = document.getElementById('backButton');
const forwardButton = document.getElementById('forwardButton');
const suggestButton = document.getElementById('suggestButton');
const resetButton = document.getElementById('resetButton');
const undoButton = document.getElementById('undoButton');
const copyFenButton = document.getElementById('copyFenButton');
const statusIndicator = document.getElementById('engine-status');
const statusText = document.getElementById('status');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderBoard();
    setupEventListeners();
    checkEngineStatus();
    updatePlayerGradeDisplay();
    setInterval(checkEngineStatus, 5000);
});

function setupEventListeners() {
    backButton.addEventListener('click', navigateBack);
    forwardButton.addEventListener('click', navigateForward);
    suggestButton.addEventListener('click', suggestMove);
    resetButton.addEventListener('click', resetBoard);
    undoButton.addEventListener('click', undoMove);
}

async function checkEngineStatus() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        engineReady = data.engine;
        updateStatusIndicator();
    } catch (e) {
        engineReady = false;
        updateStatusIndicator();
    }
}

function updateStatusIndicator() {
    if (engineReady) {
        statusIndicator.classList.add('online');
        statusText.textContent = '✅ Engine Ready';
    } else {
        statusIndicator.classList.remove('online');
        statusText.textContent = '⏳ Engine Loading...';
    }
}

function fenToBoard(fen) {
    const boardPart = fen.split(' ')[0];
    const board = [];
    const rows = boardPart.split('/');
    
    rows.forEach(row => {
        const boardRow = [];
        for (let char of row) {
            if (isNaN(char)) {
                boardRow.push(char);
            } else {
                for (let i = 0; i < parseInt(char); i++) {
                    boardRow.push('.');
                }
            }
        }
        board.push(boardRow);
    });
    
    return board;
}

function renderBoard() {
    chessboard.innerHTML = '';
    const board = fenToBoard(currentFEN);
    
    board.forEach((row, rowIdx) => {
        row.forEach((piece, colIdx) => {
            const square = document.createElement('div');
            const squareColor = (rowIdx + colIdx) % 2 === 0 ? 'light' : 'dark';
            square.className = `square ${squareColor}`;
            
            if (piece !== '.') {
                const pieceEl = document.createElement('div');
                pieceEl.className = 'piece';
                pieceEl.textContent = PIECES[piece];
                pieceEl.draggable = true;
                // Color white pieces cyan, black pieces red
                if (piece === piece.toUpperCase()) {
                    pieceEl.classList.add('white-piece');
                } else {
                    pieceEl.classList.add('black-piece');
                }
                pieceEl.addEventListener('dragstart', handleDragStart);
                pieceEl.addEventListener('dragend', handleDragEnd);
                square.appendChild(pieceEl);
            }
            
            square.dataset.square = String.fromCharCode(97 + colIdx) + (8 - rowIdx);
            square.addEventListener('dragover', handleDragOver);
            square.addEventListener('drop', handleDrop);
            square.addEventListener('dragleave', handleDragLeave);
            chessboard.appendChild(square);
        });
    });
}

async function playMove(move) {
    if (!engineReady) {
        alert('Engine not ready yet. Please wait...');
        return;
    }
    
    if (!move) return;
    
    try {
        const response = await fetch(`${API_BASE}/board`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fen: currentFEN,
                move: move
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Store previous state for undo
            moveHistory.push(currentFEN);
            currentFEN = data.fen;
            
            // Update UI
            renderBoard();
            updateAnalysis(data);
            updatePositionInfo(data);
            
            // Show analysis images on the destination square
            showAnalysisOnSquare(move, data);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (e) {
        alert('Error connecting to engine: ' + e.message);
    }
}

async function suggestMove() {
    if (!engineReady) {
        alert('Engine not ready yet. Please wait...');
        return;
    }
    
    try {
        suggestButton.disabled = true;
        suggestButton.textContent = 'Analyzing...';
        
        const response = await fetch(`${API_BASE}/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fen: currentFEN })
        });
        
        const data = await response.json();
        
        if (response.ok && data.best_move) {
            moveInput.value = data.best_move;
            moveInput.focus();
            
            // Show best line
            const bestLineSection = document.getElementById('bestLineSection');
            const bestLineEl = document.getElementById('bestLine');
            bestLineEl.textContent = data.best_line.join(' → ');
            bestLineSection.style.display = 'block';
        } else {
            alert('Could not calculate best move');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        suggestButton.disabled = false;
        suggestButton.textContent = 'Suggest Best';
    }
}

function resetBoard() {
    currentFEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    moveHistory = [];
    moveInput.value = '';
    
    // Reset grade distribution
playerGradeDistribution = {
    white: { Sigma: 0, Chad: 0, Good: 0, Okay: 0, Strange: 0, Bad: 0, Clown: 0 },
    black: { Sigma: 0, Chad: 0, Good: 0, Okay: 0, Strange: 0, Bad: 0, Clown: 0 }
};
updatePlayerGradeDisplay();
    updateGradeDistribution();
    
    // Clear move history display
    document.getElementById('moveHistory').innerHTML = '';
    
    renderBoard();
    clearAnalysis();
    undoButton.disabled = true;
    document.getElementById('fenDisplay').textContent = currentFEN;
}

function undoMove() {
    if (moveHistory.length === 0) return;
    
    currentFEN = moveHistory.pop();
    renderBoard();
    clearAnalysis();
    undoButton.disabled = moveHistory.length === 0;
    document.getElementById('fenDisplay').textContent = currentFEN;
}

function navigateBack() {
    if (moveHistory.length === 0) return;
    currentFEN = moveHistory.pop();
    renderBoard();
    clearAnalysis();
    document.getElementById('fenDisplay').textContent = currentFEN;
}

function navigateForward() {
    alert('Forward navigation not yet available');
}

async function updatePositionInfo(data) {
    const turn = data.fen.split(' ')[1] === 'w' ? 'White' : 'Black';
    const moveNumber = parseInt(data.fen.split(' ')[5]) || 1;
    
    // Calculate move counts
    // In standard chess notation: after white's move it's 1.0, after black's 1.5, etc
    let whiteMoves = moveNumber - 1;
    let blackMoves = moveNumber - 1;
    let moveCountDisplay;
    
    if (turn === 'White') {
        // It's white's turn, so black just moved
        moveCountDisplay = moveNumber - 1 + '.5';
    } else {
        // It's black's turn, so white just moved
        moveCountDisplay = moveNumber + '.0';
        blackMoves = moveNumber;
    }
    
    if (turn === 'White') {
        blackMoves = moveNumber - 1;
    } else {
        whiteMoves = moveNumber;
    }
    
    document.getElementById('moveCount').textContent = moveCountDisplay;
    document.getElementById('whiteMoves').textContent = whiteMoves;
    document.getElementById('blackMoves').textContent = blackMoves;
    document.getElementById('material').textContent = data.material || '0';
    document.getElementById('fenDisplay').textContent = data.fen;
    updateEvalBar(data.eval_after);
}

function updateEvalBar(evalCp) {
    // Clamp evaluation
    const clamped = Math.max(-500, Math.min(500, evalCp));
    const percentage = ((clamped / 500 + 1) * 50);
    
    const fill = document.getElementById('evalBarFill');
    fill.style.width = percentage + '%';
    
    const evalText = document.getElementById('evalText');
    if (Math.abs(evalCp) < 1000) {
        evalText.textContent = (evalCp / 100).toFixed(2);
    } else {
        evalText.textContent = evalCp > 0 ? '#' : '-#';
    }
}

function updateAnalysis(data) {
    const moveAnalysis = document.getElementById('moveAnalysis');
    const bestLineSection = document.getElementById('bestLineSection');
    
    // Update move info
    document.getElementById('lastMove').textContent = data.move;
    
    // Update grade with color
    const gradeEl = document.getElementById('moveGrade');
    gradeEl.textContent = data.grade;
    gradeEl.className = 'value grade-' + data.grade.toLowerCase();
    if (data.grade_color) {
        gradeEl.style.color = `rgb(${data.grade_color[0]}, ${data.grade_color[1]}, ${data.grade_color[2]})`;
    }
    
    document.getElementById('evalChange').textContent = data.eval_change > 0 ? '+' + data.eval_change : data.eval_change;
    document.getElementById('materialChange').textContent = data.material_change > 0 ? '+' + data.material_change : data.material_change;
    
    // Show hanging piece warning if present
    const hangingRow = document.getElementById('hangingRow');
    if (data.hanging_piece_value > 0) {
        document.getElementById('hanging').textContent = data.hanging_piece_value + ' pt';
        hangingRow.style.display = 'flex';
    } else {
        hangingRow.style.display = 'none';
    }
    
    // Update best line
    if (data.best_line && data.best_line.length > 0) {
        const bestLineEl = document.getElementById('bestLine');
        bestLineEl.textContent = data.best_line.join(' → ');
        bestLineSection.style.display = 'block';
    }
    
    moveAnalysis.style.display = 'block';
    addToMoveHistory(data.move, data.grade);
    // Highlight move on the board with grade symbol
// Highlight move on the board with grade image
const destSquare = data.move.slice(-2);
const squareEl = document.querySelector(`[data-square="${destSquare}"]`);
if (squareEl) {
    const gradeImages = {
        'Sigma': 'https://i.ibb.co/35W4LpDw/image.jpg',
        'Chad': 'https://i.ibb.co/3526vYdq/image.jpg',
        'Good': 'https://i.ibb.co/LXkqVyTq/image.jpg',
        'Okay': 'https://i.ibb.co/N6JWnwcP/image.jpg',
        'Strange': 'https://i.ibb.co/VWH3DPNJ/image.jpg',
        'Bad': 'https://i.ibb.co/gFb9Qkg3/image.jpg',
        'Clown': 'https://i.ibb.co/hRKhT260/image.jpg'
    };

    let badge = document.createElement('img');
    badge.className = 'grade-badge-img';
    badge.src = gradeImages[data.grade] || '';
    badge.alt = data.grade;
    badge.style.position = 'absolute';
    badge.style.top = '2px';
    badge.style.right = '2px';
    badge.style.width = '20px';
    badge.style.height = '20px';
    badge.style.pointerEvents = 'none';
    squareEl.appendChild(badge);

    // Remove badge after 3 seconds
    setTimeout(() => squareEl.removeChild(badge), 3000);
}
}

function addToMoveHistory(move, grade) {
    const historyEl = document.getElementById('moveHistory');

    const moveEl = document.createElement('div');
    moveEl.className = 'history-move grade-' + grade.toLowerCase();

    // Map grades to image URLs
    const gradeImages = {
        'Sigma': 'https://i.ibb.co/35W4LpDw/image.jpg',
        'Chad': 'https://i.ibb.co/3526vYdq/image.jpg',
        'Good': 'https://i.ibb.co/LXkqVyTq/image.jpg',
        'Okay': 'https://i.ibb.co/N6JWnwcP/image.jpg',
        'Strange': 'https://i.ibb.co/VWH3DPNJ/image.jpg',
        'Bad': 'https://i.ibb.co/gFb9Qkg3/image.jpg',
        'Clown': 'https://i.ibb.co/hRKhT260/image.jpg'
    };

    const imgSrc = gradeImages[grade] || '';

    moveEl.innerHTML = `
        <span class="move-notation">${move}</span>
        <span class="move-grade">
            <img src="${imgSrc}" alt="${grade}" class="grade-history-img"> ${grade}
        </span>
    `;

    historyEl.insertBefore(moveEl, historyEl.firstChild);

    // Update grade distribution
// Determine who made the move and update per-player count
const currentFEN = document.getElementById("fenDisplay").textContent;
const lastMoveBy = currentFEN.includes(" w ") ? "white" : "black";

if (playerGradeDistribution[lastMoveBy] && playerGradeDistribution[lastMoveBy][grade] !== undefined) {
    playerGradeDistribution[lastMoveBy][grade]++;
    updatePlayerGradeDisplay();
}
}

function updateGradeDistribution() {
    const grades = ['Sigma', 'Chad', 'Good', 'Okay', 'Strange', 'Bad', 'Clown'];
    grades.forEach(grade => {
        const countEl = document.getElementById(`gradeCount-${grade}`);
        if (countEl) {
            countEl.textContent = gradeDistribution[grade];
        }
    });
}
function updatePlayerGradeDisplay() {
    const grades = ['Sigma', 'Chad', 'Good', 'Okay', 'Strange', 'Bad', 'Clown'];
    grades.forEach(grade => {
        const whiteCell = document.getElementById(`white-${grade}`);
        const blackCell = document.getElementById(`black-${grade}`);
        if (whiteCell) whiteCell.textContent = playerGradeDistribution.white[grade];
        if (blackCell) blackCell.textContent = playerGradeDistribution.black[grade];
    });
}

function clearAnalysis() {
    document.getElementById('moveAnalysis').style.display = 'none';
    document.getElementById('bestLineSection').style.display = 'none';
    document.getElementById('moveHistory').innerHTML = '';
    updateEvalBar(0);
}

function copyFEN() {
    const fenText = document.getElementById('fenDisplay').textContent;
    navigator.clipboard.writeText(fenText).then(() => {
        const btn = copyFenButton;
        const original = btn.textContent;
        btn.textContent = '✓ Copied';
        setTimeout(() => {
            btn.textContent = original;
        }, 2000);
    });
}

// ==================== DRAG & DROP HANDLERS ====================

function handleDragStart(e) {
    draggedFrom = e.target.closest('.square').dataset.square;
    draggedPiece = e.target;
    e.target.style.opacity = '0.5';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', e.target.innerHTML);
}

function handleDragEnd(e) {
    e.target.style.opacity = '1';
    // Clear all highlights
    document.querySelectorAll('.square').forEach(square => {
        square.classList.remove('drag-over', 'drag-highlight');
    });
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    const dropSquare = e.currentTarget;
    const draggedTo = dropSquare.dataset.square;
    
if (draggedFrom && draggedTo && draggedFrom !== draggedTo) {
    const fromPiece = draggedPiece.textContent;
    const moveBase = draggedFrom + draggedTo;
    
    let move = moveBase;

    // Pawn promotion detection
    if ((fromPiece === '♟' && draggedTo[1] === '1') || // white pawn reaches 8th rank
        (fromPiece === '♟' && draggedTo[1] === '8')) { // black pawn reaches 1st rank
        // Default promote to Queen
        move += 'q'; // e.g., "e7e8q"
        // Optionally, you can prompt user:
        // const promo = prompt("Promote to (q/r/b/n)?", "q");
        // move += promo || 'q';
    }

    playMove(move);
}
    
    dropSquare.classList.remove('drag-over');
}

// Show analysis images on the square where the move was made
let analysisImageTimeout;
function showAnalysisOnSquare(move, data) {
    // move is in format like "e2e4", destination is last 2 chars
    const destinationSquare = move.slice(-2);
    const square = document.querySelector(`[data-square="${destinationSquare}"]`);
    
    if (!square) return;

    // Map grades to images
    const gradeImages = {
        'Sigma': 'https://i.ibb.co/35W4LpDw/image.jpg',
        'Chad': 'https://i.ibb.co/3526vYdq/image.jpg',
        'Good': 'https://i.ibb.co/LXkqVyTq/image.jpg',
        'Okay': 'https://i.ibb.co/N6JWnwcP/image.jpg',
        'Strange': 'https://i.ibb.co/VWH3DPNJ/image.jpg',
        'Bad': 'https://i.ibb.co/gFb9Qkg3/image.jpg',
        'Clown': 'https://i.ibb.co/hRKhT260/image.jpg'
    };

    const imgSrc = gradeImages[data.grade] || '';
    if (!imgSrc) return;

    // Create the badge image
    let badge = document.createElement('img');
    badge.src = imgSrc;
    badge.alt = data.grade;
    badge.className = 'grade-badge-img';
    badge.style.position = 'absolute';
    badge.style.top = '2px';
    badge.style.right = '2px';
    badge.style.width = '20px';
    badge.style.height = '20px';
    badge.style.pointerEvents = 'none';
    badge.style.opacity = '0';
    badge.style.transition = 'opacity 0.3s ease';

    // Append badge to the square
    square.appendChild(badge);

    // Fade in
    requestAnimationFrame(() => {
        badge.style.opacity = '1';
    });

    // Fade out and remove after 3 seconds
    setTimeout(() => {
        badge.style.opacity = '0';
        setTimeout(() => {
            if (square.contains(badge)) {
                square.removeChild(badge);
            }
        }, 300);
    }, 3000);
}

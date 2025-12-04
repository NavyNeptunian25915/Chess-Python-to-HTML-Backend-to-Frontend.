import chess
import chess.engine
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time

# --- CONFIG ---
STOCKFISH_PATH = "/Users/shreyansh/Downloads/StockfishEngine/stockfish-macos-m1-apple-silicon"

# Piece values for material calculation
PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9
}

# Move grade colors
GRADE_RGB = {
    "Sigma": (0, 255, 255),
    "Chad": (0, 255, 128),
    "Good": (0, 255, 0),
    "Okay": (128, 255, 0),
    "Strange": (255, 255, 0),
    "Bad": (255, 128, 0),
    "Clown": (255, 0, 0)
}

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Global state
engine = None
engine_process = None
event_loop = None

def initialize_engine():
    """Initialize Stockfish engine asynchronously."""
    global engine, engine_process, event_loop
    
    async def start_engine():
        global engine, engine_process
        try:
            engine_process, engine = await chess.engine.popen_uci(STOCKFISH_PATH)
            print("✅ Stockfish engine started")
        except Exception as e:
            print(f"❌ Failed to start engine: {e}")
    
    # Run in background thread
    def run_async_loop():
        global event_loop
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        event_loop.run_until_complete(start_engine())
        event_loop.run_forever()
    
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()

def material_score(board):
    """Returns material differential (White - Black) using basic piece values."""
    score = 0
    for piece, value in PIECE_VALUE.items():
        score += value * (len(board.pieces(piece, chess.WHITE)) - len(board.pieces(piece, chess.BLACK)))
    return score

def detect_hanging_piece(board):
    """Returns the value of the most valuable hanging piece that can be captured."""
    hanging_value = 0
    for move in board.legal_moves:
        if board.is_capture(move):
            captured_piece = board.piece_at(move.to_square)
            if captured_piece:
                piece_value = PIECE_VALUE.get(captured_piece.piece_type, 0)
                hanging_value = max(hanging_value, piece_value)
    return hanging_value

async def eval_position_async(board):
    """Returns Stockfish eval in centipawns, positive = White advantage."""
    if engine is None:
        return 0
    try:
        info = await engine.analyse(board, chess.engine.Limit(time=0.3))
        score = info["score"].white()
        if score.is_mate():
            return 20000 if score.mate() > 0 else -20000
        return score.cp if score.cp else 0
    except:
        return 0

def eval_position(board):
    """Synchronous wrapper for engine evaluation."""
    if event_loop is None or engine is None:
        return 0
    future = asyncio.run_coroutine_threadsafe(eval_position_async(board), event_loop)
    try:
        return future.result(timeout=2)
    except:
        return 0

def get_best_line(board):
    """Get Stockfish best line."""
    if event_loop is None or engine is None:
        return []
    
    async def get_pv():
        try:
            pv_info = await engine.analyse(board, chess.engine.Limit(time=0.3), multipv=1)
            pv_line = pv_info.get("pv", [])
            temp_board = board.copy()
            pv_moves = []
            for m in pv_line:
                if temp_board.is_legal(m):
                    pv_moves.append(temp_board.san(m))
                    temp_board.push(m)
                else:
                    break
            return pv_moves
        except:
            return []
    
    future = asyncio.run_coroutine_threadsafe(get_pv(), event_loop)
    try:
        return future.result(timeout=2)
    except:
        return []

def grade_move(board, move, eval_before, eval_after):
    """Grade a move based on evaluation change and material."""
    # Determine whose perspective we're grading from
    is_white_move = not board.turn  # Turn already changed after push
    
    # Eval change from player's perspective
    if is_white_move:
        eval_change = eval_after - eval_before
    else:
        eval_change = eval_before - eval_after
    
    # Material tracking
    board_before = board.copy()
    board_before.pop()  # Undo the move
    material_before = material_score(board_before)
    material_after = material_score(board)
    material_change = material_after - material_before
    
    # Hanging pieces
    hanging_piece_value = detect_hanging_piece(board)
    
    # Start with eval-based grading
    # Sigma sacrifice: Material lost but Stockfish approves
    if material_change < hanging_piece_value and eval_change >= -20:
        grade = "Sigma"
    # Chad capture bonus: Material gained with good eval
    elif material_change >= hanging_piece_value <= 1 and eval_change >= -40:
        grade = "Chad"
    elif eval_change >= -60:
        grade = "Good"
    elif eval_change >= -100:
        grade = "Okay"
    elif eval_change >= -200:
        grade = "Strange"
    elif eval_change >= -300:
        grade = "Bad"
    else:
        grade = "Clown"
    
    return grade, eval_change, material_change, hanging_piece_value

# ==================== API ENDPOINTS ====================

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "engine": engine is not None}), 200

@app.route('/api/board', methods=['POST'])
def analyze_move():
    """Analyze a chess move."""
    data = request.json
    fen = data.get('fen', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    move_san = data.get('move', '')
    
    try:
        board = chess.Board(fen)
        eval_before = eval_position(board)
        
        # Parse and apply move
        try:
            move = board.parse_san(move_san)
        except:
            try:
                move = board.parse_uci(move_san)
            except:
                return jsonify({"error": "Invalid move format"}), 400
        
        if move not in board.legal_moves:
            return jsonify({"error": "Illegal move"}), 400
        
        board.push(move)
        eval_after = eval_position(board)
        
        # Grade the move
        grade, eval_change, material_change, hanging = grade_move(board, move, eval_before, eval_after)
        
        # Get best line
        best_line = get_best_line(board)
        
        return jsonify({
            "fen": board.fen(),
            "move": move_san,
            "eval_before": eval_before,
            "eval_after": eval_after,
            "eval_change": eval_change,
            "material_change": material_change,
            "hanging_piece_value": hanging,
            "grade": grade,
            "grade_color": GRADE_RGB.get(grade),
            "best_line": best_line,
            "is_game_over": board.is_game_over(),
            "result": board.result() if board.is_game_over() else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    """Evaluate a position."""
    data = request.json
    fen = data.get('fen', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    
    try:
        board = chess.Board(fen)
        eval_cp = eval_position(board)
        material = material_score(board)
        
        return jsonify({
            "fen": fen,
            "eval": eval_cp,
            "material": material,
            "legal_moves": len(list(board.legal_moves)),
            "turn": "White" if board.turn else "Black"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/moves', methods=['POST'])
def get_legal_moves():
    """Get legal moves for a position."""
    data = request.json
    fen = data.get('fen', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    
    try:
        board = chess.Board(fen)
        moves = [move.uci() for move in board.legal_moves]
        return jsonify({"moves": moves}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/suggest', methods=['POST'])
def suggest_move():
    """Suggest best move for a position."""
    data = request.json
    fen = data.get('fen', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    
    try:
        board = chess.Board(fen)
        best_line = get_best_line(board)
        if best_line:
            return jsonify({
                "best_move": best_line[0],
                "best_line": best_line
            }), 200
        else:
            return jsonify({"error": "Could not calculate best move"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/reset', methods=['POST'])
def reset_board():
    """Reset to starting position."""
    return jsonify({
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    }), 200

if __name__ == "__main__":
    print("Initializing Chess Backend Server...")
    initialize_engine()
    
    # Give engine time to start
    time.sleep(2)
    
    print("Starting Flask server on http://localhost:6400")
    app.run(debug=True, host='0.0.0.0', port=6400, threaded=True)

#!/usr/bin/env python3
"""
Synchronous Flask + Stockfish backend for chess analysis.
Copy & paste this file as `aiserver.py`. Make sure STOCKFISH_PATH points
to your Stockfish binary. This version uses synchronous engine calls
(SimpleEngine) so it's robust on macOS and avoids asyncio/thread issues.
"""

import chess
import chess.engine
from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import atexit
import os

# ---------------- CONFIG ----------------
STOCKFISH_PATH = "/Users/shreyansh/Downloads/StockfishEngine/stockfish-macos-m1-apple-silicon"

PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9
}

GRADE_RGB = {
    "Sigma": (0, 255, 255),
    "Chad": (0, 255, 128),
    "Good": (0, 255, 0),
    "Okay": (128, 255, 0),
    "Strange": (255, 255, 0),
    "Bad": (255, 128, 0),
    "Clown": (255, 0, 0)
}

# ---------------- APP ----------------
app = Flask(__name__)
CORS(app)

engine = None


# ---------------- ENGINE LIFECYCLE ----------------
def initialize_engine():
    """Start Stockfish synchronously. Prints error if it fails."""
    global engine
    try:
        if not os.path.exists(STOCKFISH_PATH):
            raise FileNotFoundError(f"Stockfish binary not found at: {STOCKFISH_PATH}")
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        print("✅ Stockfish engine started (synchronous).")
    except Exception as e:
        engine = None
        print(f"❌ Failed to start Stockfish engine: {e}")


@atexit.register
def close_engine():
    global engine
    if engine:
        try:
            engine.quit()
            print("✅ Stockfish engine shut down.")
        except Exception:
            pass


# ---------------- UTILITIES ----------------
def material_score(board: chess.Board) -> int:
    """Material score White - Black using PIECE_VALUE."""
    score = 0
    for piece, value in PIECE_VALUE.items():
        score += value * (len(board.pieces(piece, chess.WHITE)) - len(board.pieces(piece, chess.BLACK)))
    return score


def detect_hanging_piece(board: chess.Board) -> int:
    """Return highest-value capture available among legal moves (0 if none)."""
    max_val = 0
    for mv in board.legal_moves:
        if board.is_capture(mv):
            captured = board.piece_at(mv.to_square)
            if captured:
                max_val = max(max_val, PIECE_VALUE.get(captured.piece_type, 0))
    return max_val


def eval_position(board: chess.Board, think_time: float = 0.3) -> int:
    """
    Return evaluation in centipawns from White's perspective.
    Large positive = White winning, large negative = Black winning.
    Mate is represented by a very large value.
    """
    if engine is None:
        return 0
    try:
        info = engine.analyse(board, chess.engine.Limit(time=think_time))
        score = info.get("score")
        if score is None:
            return 0
        score = score.white()
        if score.is_mate():
            # Positive if White mating, negative if Black mating
            return 100000 if score.mate() > 0 else -100000
        return score.cp if score.cp is not None else 0
    except Exception:
        return 0


def get_best_line(board: chess.Board, think_time: float = 0.5):
    """Return best line as a list of SAN moves (may be empty)."""
    if engine is None:
        return []
    try:
        info = engine.analyse(board, chess.engine.Limit(time=think_time), multipv=1)
        pv = info.get("pv", [])
        temp = board.copy()
        san_moves = []
        for m in pv:
            if temp.is_legal(m):
                san_moves.append(temp.san(m))
                temp.push(m)
            else:
                break
        return san_moves
    except Exception:
        return []


def parse_move_with_promotions(board: chess.Board, move_str: str):
    """
    Try to parse a move string robustly:
      - Try UCI (e7e8q)
      - Try SAN (e8=Q or Qxe8 etc.)
      - If input looks like 'e8=Q', convert to 'e7e8q' heuristically when possible
    Returns a chess.Move or raises ValueError.
    """
    move = None
    # Try direct UCI first (covers e7e8q)
    try:
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves:
            return move
    except Exception:
        move = None

    # Try board.parse_uci (some formats)
    try:
        move = board.parse_uci(move_str)
        if move in board.legal_moves:
            return move
    except Exception:
        move = None

    # Try SAN
    try:
        move = board.parse_san(move_str)
        if move in board.legal_moves:
            return move
    except Exception:
        move = None

    # Handle SAN like 'e8=Q' or 'e8Q' by constructing UCI if possible:
    # Find any pawn on the previous rank that can move to the destination and promote.
    # This is a best-effort fallback.
    # Accept both uppercase and lowercase promotion letters.
    s = move_str.strip()
    if len(s) >= 2 and ('=' in s or s[-1].lower() in ['q', 'r', 'b', 'n']):
        # Extract destination square and promotion piece
        dest = None
        promo = None
        if '=' in s:
            parts = s.split('=')
            dest = parts[0][-2:]
            promo = parts[1][0].lower()
        else:
            dest = s[-2:]
            promo = s[-1].lower()

        # Find pawn that can move to dest
        dest_sq = chess.parse_square(dest)
        for from_sq in board.pieces(chess.PAWN, board.turn):
            mv = chess.Move(from_sq, dest_sq, promotion={'q': chess.QUEEN, 'r': chess.ROOK, 'b': chess.BISHOP, 'n': chess.KNIGHT}.get(promo))
            if mv in board.legal_moves:
                return mv

    raise ValueError("Could not parse move: " + move_str)


def grade_move(board_after: chess.Board, move: chess.Move, eval_before: int, eval_after: int):
    """
    Grade a move after it has been pushed onto the board (board_after).
    Returns: (grade_str, eval_change_from_player_perspective, material_change, hanging_value)
    """
    # Turn already switched after push; the player who moved is the opposite of board.turn
    is_white_move = not board_after.turn

    # Eval change from the mover's perspective
    eval_change = (eval_after - eval_before) if is_white_move else (eval_before - eval_after)

    # Material change
    board_before = board_after.copy()
    board_before.pop()
    material_change = material_score(board_after) - material_score(board_before)

    hanging = detect_hanging_piece(board_after)

    # If game over, give strong grades for winning moves
    if board_after.is_game_over():
        res = board_after.result()
        if res == "1-0":
            grade = "Sigma" if is_white_move else "Clown"
        elif res == "0-1":
            grade = "Sigma" if not is_white_move else "Clown"
        else:
            grade = "Good"
        return grade, eval_change, material_change, hanging

    # Normal grading heuristics
    if material_change < hanging and eval_change >= -20:
        grade = "Sigma"
    elif material_change >= hanging and eval_change >= -40:
        # captured material and evaluation improved
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

    return grade, eval_change, material_change, hanging


# ---------------- API ENDPOINTS ----------------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "engine": engine is not None}), 200


@app.route("/api/board", methods=["POST"])
def analyze_move():
    """
    Payload:
      { "fen": <optional FEN>, "move": <SAN or UCI move string> }
    Returns evaluation + grading + best line.
    """
    data = request.json or {}
    fen = data.get("fen", chess.STARTING_FEN)
    move_input = data.get("move", "")

    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": f"Invalid FEN: {e}"}), 400

    eval_before = eval_position(board)

    # parse move robustly
    try:
        move = parse_move_with_promotions(board, move_input)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if move not in board.legal_moves:
        return jsonify({"error": "Illegal move"}), 400

    # apply move
    board.push(move)
    eval_after = eval_position(board)

    grade, eval_change, material_change, hanging = grade_move(board, move, eval_before, eval_after)
    best_line = get_best_line(board)

    return jsonify({
        "fen": board.fen(),
        "move": move_input,
        "move_uci": move.uci(),
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


@app.route("/api/evaluate", methods=["POST"])
def evaluate():
    data = request.json or {}
    fen = data.get("fen", chess.STARTING_FEN)
    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": f"Invalid FEN: {e}"}), 400

    return jsonify({
        "fen": fen,
        "eval": eval_position(board),
        "material": material_score(board),
        "legal_moves": len(list(board.legal_moves)),
        "turn": "White" if board.turn else "Black"
    }), 200


@app.route("/api/moves", methods=["POST"])
def get_legal_moves():
    data = request.json or {}
    fen = data.get("fen", chess.STARTING_FEN)
    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": f"Invalid FEN: {e}"}), 400

    moves = [m.uci() for m in board.legal_moves]
    return jsonify({"moves": moves}), 200


@app.route("/api/suggest", methods=["POST"])
def suggest_move():
    data = request.json or {}
    fen = data.get("fen", chess.STARTING_FEN)
    try:
        board = chess.Board(fen)
    except Exception as e:
        return jsonify({"error": f"Invalid FEN: {e}"}), 400

    best_line = get_best_line(board)
    if not best_line:
        return jsonify({"error": "Could not calculate best move"}), 400
    return jsonify({"best_move": best_line[0], "best_line": best_line}), 200


@app.route("/api/reset", methods=["POST"])
def reset_board():
    return jsonify({"fen": chess.STARTING_FEN}), 200


# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("Initializing Chess Backend Server...")
    initialize_engine()
    # give a small moment if engine was just started
    time.sleep(0.5)
    print("Starting Flask server on http://localhost:6400")
    app.run(debug=True, host="0.0.0.0", port=6400, threaded=True)

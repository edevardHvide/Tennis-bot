import { useState, useEffect, useRef, useCallback } from 'react';

interface PongGameProps {
  onClose: () => void;
}

// Canvas & court
const CANVAS_W = 600;
const CANVAS_H = 400;
const COURT_GREEN = '#2d5a27';
const NET_COLOR = 'rgba(255, 255, 255, 0.35)';
const LINE_COLOR = 'rgba(255, 255, 255, 0.15)';

// Paddles (tennis rackets)
const PADDLE_W = 14;
const PADDLE_H = 80;
const PADDLE_MARGIN = 20;
const PADDLE_COLOR = '#e8d44d'; // gold handle
const PADDLE_HEAD_PLAYER = '#4ade80'; // green head
const PADDLE_HEAD_AI = '#f87171'; // red head
const PADDLE_SPEED = 6;

// Ball (tennis ball)
const BALL_RADIUS = 8;
const BALL_COLOR = '#ccff00';
const BALL_SEAM = '#a3cc00';

// Game rules
const WIN_SCORE = 3;
const BASE_BALL_SPEED = 4.5;
const SPEED_INCREMENT = 0.8; // per point scored in a rally

// AI
const AI_REACTION = 0.04; // how quickly AI tracks ball (0-1)

type GameState = 'waiting' | 'playing' | 'scored' | 'won';

interface Ball {
  x: number;
  y: number;
  vx: number;
  vy: number;
  speed: number;
}

export default function PongGame({ onClose }: PongGameProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  // Game state refs (for animation loop)
  const playerYRef = useRef(CANVAS_H / 2 - PADDLE_H / 2);
  const aiYRef = useRef(CANVAS_H / 2 - PADDLE_H / 2);
  const ballRef = useRef<Ball>({
    x: CANVAS_W / 2,
    y: CANVAS_H / 2,
    vx: BASE_BALL_SPEED,
    vy: 0,
    speed: BASE_BALL_SPEED,
  });
  const playerScoreRef = useRef(0);
  const aiScoreRef = useRef(0);
  const gameStateRef = useRef<GameState>('waiting');
  const keysRef = useRef<Set<string>>(new Set());
  const totalPointsRef = useRef(0); // total points scored in game, for speed scaling
  const touchYRef = useRef<number | null>(null);

  const [playerScore, setPlayerScore] = useState(0);
  const [aiScore, setAiScore] = useState(0);
  const [gameState, setGameState] = useState<GameState>('waiting');
  const [winner, setWinner] = useState<'player' | 'ai' | null>(null);

  const resetBall = useCallback((direction: 1 | -1) => {
    const angle = (Math.random() * 0.8 - 0.4); // random angle between -0.4 and 0.4 rad
    const currentSpeed = BASE_BALL_SPEED + totalPointsRef.current * SPEED_INCREMENT;
    ballRef.current = {
      x: CANVAS_W / 2,
      y: CANVAS_H / 2,
      vx: Math.cos(angle) * currentSpeed * direction,
      vy: Math.sin(angle) * currentSpeed,
      speed: currentSpeed,
    };
  }, []);

  const startGame = useCallback(() => {
    playerScoreRef.current = 0;
    aiScoreRef.current = 0;
    totalPointsRef.current = 0;
    setPlayerScore(0);
    setAiScore(0);
    setWinner(null);
    playerYRef.current = CANVAS_H / 2 - PADDLE_H / 2;
    aiYRef.current = CANVAS_H / 2 - PADDLE_H / 2;
    resetBall(1);
    gameStateRef.current = 'playing';
    setGameState('playing');
  }, [resetBall]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Court background
    ctx.fillStyle = COURT_GREEN;
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // Court boundary lines
    ctx.strokeStyle = LINE_COLOR;
    ctx.lineWidth = 2;
    ctx.strokeRect(4, 4, CANVAS_W - 8, CANVAS_H - 8);

    // Center line (net)
    ctx.strokeStyle = NET_COLOR;
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 8]);
    ctx.beginPath();
    ctx.moveTo(CANVAS_W / 2, 0);
    ctx.lineTo(CANVAS_W / 2, CANVAS_H);
    ctx.stroke();
    ctx.setLineDash([]);

    // Net posts
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.fillRect(CANVAS_W / 2 - 3, 0, 6, 6);
    ctx.fillRect(CANVAS_W / 2 - 3, CANVAS_H - 6, 6, 6);

    // Draw paddle (tennis racket style)
    const drawPaddle = (x: number, y: number, headColor: string) => {
      // Racket head (oval)
      ctx.fillStyle = headColor;
      ctx.beginPath();
      ctx.ellipse(x + PADDLE_W / 2, y + PADDLE_H * 0.4, PADDLE_W / 2 + 2, PADDLE_H * 0.4, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.3)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Strings (horizontal)
      ctx.strokeStyle = 'rgba(255,255,255,0.2)';
      ctx.lineWidth = 0.8;
      for (let i = 1; i < 6; i++) {
        const sy = y + (PADDLE_H * 0.8 * i) / 6;
        const halfW = Math.sqrt(Math.max(0, 1 - Math.pow((sy - (y + PADDLE_H * 0.4)) / (PADDLE_H * 0.4), 2))) * (PADDLE_W / 2 + 2);
        ctx.beginPath();
        ctx.moveTo(x + PADDLE_W / 2 - halfW, sy);
        ctx.lineTo(x + PADDLE_W / 2 + halfW, sy);
        ctx.stroke();
      }
      // Strings (vertical)
      for (let i = 1; i < 4; i++) {
        const sx = x + (PADDLE_W * i) / 4 + (PADDLE_W / 2 - PADDLE_W / 4);
        ctx.beginPath();
        ctx.moveTo(sx, y + 4);
        ctx.lineTo(sx, y + PADDLE_H * 0.78);
        ctx.stroke();
      }

      // Handle (grip)
      ctx.fillStyle = PADDLE_COLOR;
      ctx.beginPath();
      ctx.roundRect(x + PADDLE_W / 2 - 3, y + PADDLE_H * 0.75, 6, PADDLE_H * 0.25, 2);
      ctx.fill();
      ctx.fillStyle = '#c4a830';
      // grip texture
      for (let i = 0; i < 3; i++) {
        ctx.fillRect(x + PADDLE_W / 2 - 2, y + PADDLE_H * 0.78 + i * 5, 4, 2);
      }
    };

    // Player paddle (left)
    drawPaddle(PADDLE_MARGIN, playerYRef.current, PADDLE_HEAD_PLAYER);

    // AI paddle (right)
    drawPaddle(CANVAS_W - PADDLE_MARGIN - PADDLE_W, aiYRef.current, PADDLE_HEAD_AI);

    // Ball (tennis ball)
    const ball = ballRef.current;
    ctx.fillStyle = BALL_COLOR;
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, BALL_RADIUS, 0, Math.PI * 2);
    ctx.fill();
    // Ball seam
    ctx.strokeStyle = BALL_SEAM;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, BALL_RADIUS - 3, -0.5, 1.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, BALL_RADIUS - 3, Math.PI - 0.5, Math.PI + 1.2);
    ctx.stroke();

    // Score display
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.font = 'bold 36px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${playerScoreRef.current}`, CANVAS_W / 4, 50);
    ctx.fillText(`${aiScoreRef.current}`, (CANVAS_W * 3) / 4, 50);

    // Labels
    ctx.font = '12px system-ui, sans-serif';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.fillText('YOU', CANVAS_W / 4, 70);
    ctx.fillText('CPU', (CANVAS_W * 3) / 4, 70);
  }, []);

  const update = useCallback(() => {
    if (gameStateRef.current !== 'playing') return;

    const keys = keysRef.current;

    // Player movement (keyboard)
    if (keys.has('ArrowUp') || keys.has('w') || keys.has('W')) {
      playerYRef.current = Math.max(0, playerYRef.current - PADDLE_SPEED);
    }
    if (keys.has('ArrowDown') || keys.has('s') || keys.has('S')) {
      playerYRef.current = Math.min(CANVAS_H - PADDLE_H, playerYRef.current + PADDLE_SPEED);
    }

    // Player movement (touch)
    if (touchYRef.current !== null) {
      const targetY = touchYRef.current - PADDLE_H / 2;
      const clampedTarget = Math.max(0, Math.min(CANVAS_H - PADDLE_H, targetY));
      const diff = clampedTarget - playerYRef.current;
      playerYRef.current += diff * 0.3; // smooth follow
    }

    // AI movement — track ball with reaction delay
    const ball = ballRef.current;
    const aiCenter = aiYRef.current + PADDLE_H / 2;
    const diff = ball.y - aiCenter;
    aiYRef.current += diff * AI_REACTION;
    aiYRef.current = Math.max(0, Math.min(CANVAS_H - PADDLE_H, aiYRef.current));

    // Ball movement
    ball.x += ball.vx;
    ball.y += ball.vy;

    // Top/bottom bounce
    if (ball.y - BALL_RADIUS <= 0) {
      ball.y = BALL_RADIUS;
      ball.vy = Math.abs(ball.vy);
    }
    if (ball.y + BALL_RADIUS >= CANVAS_H) {
      ball.y = CANVAS_H - BALL_RADIUS;
      ball.vy = -Math.abs(ball.vy);
    }

    // Paddle collision — player (left)
    const playerPaddleRight = PADDLE_MARGIN + PADDLE_W;
    if (
      ball.vx < 0 &&
      ball.x - BALL_RADIUS <= playerPaddleRight &&
      ball.x + BALL_RADIUS >= PADDLE_MARGIN &&
      ball.y >= playerYRef.current &&
      ball.y <= playerYRef.current + PADDLE_H
    ) {
      ball.x = playerPaddleRight + BALL_RADIUS;
      const hitPos = (ball.y - playerYRef.current) / PADDLE_H - 0.5; // -0.5 to 0.5
      const angle = hitPos * (Math.PI / 3); // max 60 degrees
      ball.vx = Math.cos(angle) * ball.speed;
      ball.vy = Math.sin(angle) * ball.speed;
    }

    // Paddle collision — AI (right)
    const aiPaddleLeft = CANVAS_W - PADDLE_MARGIN - PADDLE_W;
    if (
      ball.vx > 0 &&
      ball.x + BALL_RADIUS >= aiPaddleLeft &&
      ball.x - BALL_RADIUS <= CANVAS_W - PADDLE_MARGIN &&
      ball.y >= aiYRef.current &&
      ball.y <= aiYRef.current + PADDLE_H
    ) {
      ball.x = aiPaddleLeft - BALL_RADIUS;
      const hitPos = (ball.y - aiYRef.current) / PADDLE_H - 0.5;
      const angle = hitPos * (Math.PI / 3);
      ball.vx = -Math.cos(angle) * ball.speed;
      ball.vy = Math.sin(angle) * ball.speed;
    }

    // Score — ball past left edge (AI scores)
    if (ball.x < -BALL_RADIUS) {
      aiScoreRef.current += 1;
      totalPointsRef.current += 1;
      setAiScore(aiScoreRef.current);
      if (aiScoreRef.current >= WIN_SCORE) {
        gameStateRef.current = 'won';
        setGameState('won');
        setWinner('ai');
      } else {
        resetBall(1); // serve towards player
      }
    }

    // Score — ball past right edge (Player scores)
    if (ball.x > CANVAS_W + BALL_RADIUS) {
      playerScoreRef.current += 1;
      totalPointsRef.current += 1;
      setPlayerScore(playerScoreRef.current);
      if (playerScoreRef.current >= WIN_SCORE) {
        gameStateRef.current = 'won';
        setGameState('won');
        setWinner('player');
      } else {
        resetBall(-1); // serve towards AI
      }
    }
  }, [resetBall]);

  // Game loop
  useEffect(() => {
    const loop = () => {
      update();
      draw();
      animRef.current = requestAnimationFrame(loop);
    };
    animRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animRef.current);
  }, [update, draw]);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'w', 'W', 's', 'S'].includes(e.key)) {
        e.preventDefault();
        keysRef.current.add(e.key);
      }
      // Space to start/restart
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        if (gameStateRef.current === 'waiting' || gameStateRef.current === 'won') {
          startGame();
        }
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      keysRef.current.delete(e.key);
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [startGame]);

  // Touch controls
  const handleTouchMove = (e: React.TouchEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleY = CANVAS_H / rect.height;
    touchYRef.current = (e.touches[0].clientY - rect.top) * scaleY;
  };

  const handleTouchEnd = () => {
    touchYRef.current = null;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span className="text-2xl">🏓</span> Pong
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Game canvas */}
        <div className="flex justify-center mb-4 relative">
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
            className="rounded-lg border-2 border-green-700 dark:border-green-600"
            style={{ maxWidth: '100%', aspectRatio: `${CANVAS_W}/${CANVAS_H}`, touchAction: 'none' }}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          />

          {/* Waiting overlay */}
          {gameState === 'waiting' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className="text-white text-2xl font-bold drop-shadow-lg mb-2">Tennis Pong</p>
                <p className="text-white/80 text-sm drop-shadow mb-4">First to {WIN_SCORE} points wins!</p>
                <button
                  onClick={startGame}
                  className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded-lg transition-colors shadow-lg"
                >
                  Start Game
                </button>
                <p className="text-white/60 text-xs mt-3 drop-shadow">Press Space or Enter</p>
              </div>
            </div>
          )}

          {/* Win/lose overlay */}
          {gameState === 'won' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <p className={`text-3xl font-bold drop-shadow-lg mb-1 ${winner === 'player' ? 'text-green-400' : 'text-red-400'}`}>
                  {winner === 'player' ? 'You Win!' : 'Game Over'}
                </p>
                <p className="text-white text-xl font-bold drop-shadow mb-4">
                  {playerScore} — {aiScore}
                </p>
                <button
                  onClick={startGame}
                  className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded-lg transition-colors shadow-lg"
                >
                  Play Again
                </button>
                <p className="text-white/60 text-xs mt-3 drop-shadow">Press Space or Enter</p>
              </div>
            </div>
          )}
        </div>

        {/* Controls hint */}
        {gameState === 'playing' && (
          <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
            Arrow Up/Down or W/S to move your paddle. Touch &amp; drag on mobile.
          </p>
        )}
      </div>
    </div>
  );
}

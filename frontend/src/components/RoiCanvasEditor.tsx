import { MouseEvent, useEffect, useRef } from "react";

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;

type RoiCanvasEditorProps = {
  snapshotUrl: string | null;
  points: number[][];
  existingZones: number[][][];
  onAddPoint: (point: number[]) => void;
  onClear: () => void;
  onSave: () => void;
  saving: boolean;
  disabled?: boolean;
};

function drawPlaceholder(ctx: CanvasRenderingContext2D): void {
  const gradient = ctx.createLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
  gradient.addColorStop(0, "#1f3344");
  gradient.addColorStop(1, "#374d61");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

  ctx.fillStyle = "rgba(255,255,255,0.14)";
  for (let x = 0; x < CANVAS_WIDTH; x += 40) {
    ctx.fillRect(x, 0, 1, CANVAS_HEIGHT);
  }
  for (let y = 0; y < CANVAS_HEIGHT; y += 40) {
    ctx.fillRect(0, y, CANVAS_WIDTH, 1);
  }

  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.font = "700 20px DM Sans";
  ctx.fillText("Нет доступного снимка камеры", 28, 42);
  ctx.font = "400 14px DM Sans";
  ctx.fillText("Можно рисовать ROI поверх плейсхолдера и сохранить зону", 28, 66);
}

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  points: number[][],
  options: { strokeStyle: string; fillStyle: string; pointColor: string; showPoints: boolean },
): void {
  if (points.length === 0) {
    return;
  }

  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  points.slice(1).forEach((point) => ctx.lineTo(point[0], point[1]));
  if (points.length >= 3) {
    ctx.closePath();
  }

  ctx.strokeStyle = options.strokeStyle;
  ctx.lineWidth = 2;
  ctx.stroke();
  if (points.length >= 3) {
    ctx.fillStyle = options.fillStyle;
    ctx.fill();
  }

  if (!options.showPoints) {
    return;
  }
  points.forEach((point) => {
    ctx.beginPath();
    ctx.arc(point[0], point[1], 4.5, 0, Math.PI * 2);
    ctx.fillStyle = options.pointColor;
    ctx.fill();
  });
}

export function RoiCanvasEditor({
  snapshotUrl,
  points,
  existingZones,
  onAddPoint,
  onClear,
  onSave,
  saving,
  disabled = false,
}: RoiCanvasEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    let isDisposed = false;
    const draw = (image: HTMLImageElement | null) => {
      if (isDisposed) {
        return;
      }
      ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

      if (image) {
        ctx.drawImage(image, 0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
      } else {
        drawPlaceholder(ctx);
      }

      existingZones.forEach((zone) =>
        drawPolygon(ctx, zone, {
          strokeStyle: "rgba(32, 194, 212, 0.95)",
          fillStyle: "rgba(32, 194, 212, 0.20)",
          pointColor: "rgba(32, 194, 212, 0.95)",
          showPoints: false,
        }),
      );

      drawPolygon(ctx, points, {
        strokeStyle: "rgba(244, 157, 55, 0.98)",
        fillStyle: "rgba(244, 157, 55, 0.26)",
        pointColor: "#f49d37",
        showPoints: true,
      });
    };

    if (!snapshotUrl) {
      draw(null);
      return () => {
        isDisposed = true;
      };
    }

    const image = new Image();
    image.onload = () => draw(image);
    image.onerror = () => draw(null);
    image.src = snapshotUrl;

    return () => {
      isDisposed = true;
    };
  }, [existingZones, points, snapshotUrl]);

  const handleCanvasClick = (event: MouseEvent<HTMLCanvasElement>) => {
    if (disabled) {
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const scaleX = CANVAS_WIDTH / rect.width;
    const scaleY = CANVAS_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);
    onAddPoint([x, y]);
  };

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-2xl border border-slate-300 bg-slate-900/10">
        <canvas
          ref={canvasRef}
          width={CANVAS_WIDTH}
          height={CANVAS_HEIGHT}
          onClick={handleCanvasClick}
          className={`aspect-video w-full ${disabled ? "cursor-not-allowed opacity-70" : "cursor-crosshair"}`}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-600">
          Точек: <span className="font-semibold">{points.length}</span>. Кликните по изображению, чтобы построить полигон.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClear}
            disabled={disabled || points.length === 0}
            className="rounded-xl border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Очистить
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={disabled || points.length < 3 || saving}
            className="rounded-xl bg-ember px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? "Сохранение..." : "Сохранить ROI"}
          </button>
        </div>
      </div>
    </div>
  );
}

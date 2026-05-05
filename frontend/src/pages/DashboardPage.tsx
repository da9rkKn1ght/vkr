import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { apiRequest } from "../lib/api";
import { WS_URL } from "../lib/config";
import type { Camera, Incident, IncidentListResponse, WsIncidentCreatedPayload } from "../types";

type WsState = "connecting" | "connected" | "disconnected";

function isToday(dateRaw: string): boolean {
  const date = new Date(dateRaw);
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

function wsLabel(status: WsState): string {
  if (status === "connected") {
    return "подключен";
  }
  if (status === "connecting") {
    return "подключение";
  }
  return "отключен";
}

function incidentTypeLabel(type: Incident["type"]): string {
  switch (type) {
    case "sleep":
      return "Сон";
    case "absence":
      return "Отсутствие";
    case "phone":
      return "Телефон";
    case "smoking":
      return "Курение";
    case "anomalous_movement":
      return "Аномальное движение";
    default:
      return type;
  }
}

export function DashboardPage() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<WsState>("connecting");
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);

  const [totalIncidents, setTotalIncidents] = useState(0);
  const [incidentsToday, setIncidentsToday] = useState(0);
  const [activeCameras, setActiveCameras] = useState(0);

  const wsUrl = useMemo(() => {
    if (!accessToken) {
      return null;
    }
    const url = new URL(WS_URL);
    url.searchParams.set("token", accessToken);
    return url.toString();
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      return;
    }
    let mounted = true;

    (async () => {
      try {
        const [cameraList, incidentPage] = await Promise.all([
          apiRequest<Camera[]>("/cameras", { token: accessToken }),
          apiRequest<IncidentListResponse>("/incidents", {
            token: accessToken,
            params: { page: 1, page_size: 100 },
          }),
        ]);

        if (!mounted) {
          return;
        }

        setActiveCameras(cameraList.filter((camera) => camera.is_active).length);
        setTotalIncidents(incidentPage.total);
        setIncidentsToday(incidentPage.items.filter((incident) => isToday(incident.timestamp)).length);
        setRecentIncidents(incidentPage.items.slice(0, 8));
      } catch (error) {
        const message = error instanceof Error ? error.message : "Не удалось загрузить данные дашборда";
        toast.error(message);
      }
    })();

    return () => {
      mounted = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!wsUrl) {
      return;
    }

    let reconnectAttempts = 0;
    let reconnectTimer: number | undefined;
    let activeSocket: WebSocket | null = null;
    let closedByEffect = false;

    const connect = () => {
      if (closedByEffect) {
        return;
      }

      setStatus("connecting");
      const socket = new WebSocket(wsUrl);
      activeSocket = socket;

      socket.onopen = () => {
        reconnectAttempts = 0;
        setStatus("connected");
      };

      socket.onclose = () => {
        if (closedByEffect) {
          return;
        }

        setStatus("disconnected");
        const delayMs = Math.min(15000, 1000 * 2 ** reconnectAttempts);
        reconnectAttempts += 1;
        reconnectTimer = window.setTimeout(() => connect(), delayMs);
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as WsIncidentCreatedPayload;
          if (payload.event !== "incident_created" || !payload.data) {
            return;
          }

          const incident = payload.data;
          setRecentIncidents((prev) => [incident, ...prev.filter((item) => item.id !== incident.id)].slice(0, 8));
          setTotalIncidents((prev) => prev + 1);
          if (isToday(incident.timestamp)) {
            setIncidentsToday((prev) => prev + 1);
          }

          toast.success(`Новый инцидент: камера #${incident.camera_id}, ${incidentTypeLabel(incident.type)}`, {
            duration: 5000,
          });
        } catch {
          // ignore malformed websocket payload
        }
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      activeSocket?.close();
    };
  }, [wsUrl]);

  return (
    <section className="space-y-8">
      <div className="rounded-3xl border border-white/60 bg-white/80 p-6 shadow-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-ink">Панель мониторинга</h1>
            <p className="mt-2 text-sm text-slate-600">Онлайн-контроль инцидентов по камерам в реальном времени.</p>
          </div>
          <div
            className={`rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-wider ${
              status === "connected"
                ? "bg-accent/15 text-accent"
                : status === "connecting"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-rose-100 text-rose-700"
            }`}
          >
            WS: {wsLabel(status)}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-2xl border border-white/60 bg-white/85 p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-slate-500">Инцидентов сегодня</p>
          <p className="mt-3 text-3xl font-bold text-ink">{incidentsToday}</p>
        </article>
        <article className="rounded-2xl border border-white/60 bg-white/85 p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-slate-500">Активные камеры</p>
          <p className="mt-3 text-3xl font-bold text-ink">{activeCameras}</p>
        </article>
        <article className="rounded-2xl border border-white/60 bg-white/85 p-5 shadow-panel">
          <p className="text-xs uppercase tracking-wide text-slate-500">Всего инцидентов</p>
          <p className="mt-3 text-3xl font-bold text-ink">{totalIncidents}</p>
        </article>
      </div>

      <section className="rounded-3xl border border-white/60 bg-white/80 p-6 shadow-panel">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold text-ink">Последние оповещения</h2>
          <Link to="/incidents" className="text-sm font-semibold text-accent hover:underline">
            Открыть журнал
          </Link>
        </div>
        {recentIncidents.length === 0 ? (
          <p className="text-sm text-slate-500">Пока нет событий для отображения.</p>
        ) : (
          <ul className="space-y-3">
            {recentIncidents.map((incident) => (
              <li key={incident.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-sm font-semibold text-ink">
                  Камера #{incident.camera_id} - {incidentTypeLabel(incident.type)}
                </p>
                <p className="text-xs text-slate-500">{new Date(incident.timestamp).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}

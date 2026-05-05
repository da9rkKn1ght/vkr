import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";

import { useAuth } from "../auth/AuthContext";
import { apiRequest } from "../lib/api";
import { resolveImageUrl } from "../lib/config";
import type { Incident, IncidentListResponse, IncidentType } from "../types";

const PAGE_SIZE = 10;
const INCIDENT_TYPES: IncidentType[] = ["sleep", "absence", "phone", "smoking", "anomalous_movement"];

export function IncidentsPage() {
  const { accessToken } = useAuth();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [cameraId, setCameraId] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const loadIncidents = useCallback(async () => {
    if (!accessToken) {
      return;
    }
    setLoading(true);
    try {
      const response = await apiRequest<IncidentListResponse>("/incidents", {
        token: accessToken,
        params: {
          page,
          page_size: PAGE_SIZE,
          camera_id: cameraId || undefined,
          type: typeFilter || undefined,
        },
      });
      setIncidents(response.items);
      setTotal(response.total);
    } catch {
      toast.error("Не удалось загрузить инциденты");
    } finally {
      setLoading(false);
    }
  }, [accessToken, cameraId, page, typeFilter]);

  useEffect(() => {
    void loadIncidents();
  }, [loadIncidents]);

  useEffect(() => {
    setPage(1);
  }, [cameraId, typeFilter]);

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-white/60 bg-white/80 p-6 shadow-panel">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink">История инцидентов</h1>
        <p className="mt-2 text-sm text-slate-600">Пагинированный журнал с фильтрацией по камере и типу события.</p>
      </div>

      <div className="grid gap-4 rounded-3xl border border-white/60 bg-white/80 p-4 shadow-panel md:grid-cols-[1fr_1fr_auto]">
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">ID камеры</span>
          <input
            value={cameraId}
            onChange={(event) => setCameraId(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none ring-accent focus:border-accent focus:ring-2"
            placeholder="например, 1"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">Тип</span>
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none ring-accent focus:border-accent focus:ring-2"
          >
            <option value="">Все</option>
            {INCIDENT_TYPES.map((incidentType) => (
              <option key={incidentType} value={incidentType}>
                {incidentType}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void loadIncidents()}
          className="self-end rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          Обновить
        </button>
      </div>

      <div className="overflow-hidden rounded-3xl border border-white/60 bg-white/85 shadow-panel">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-100 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-4 py-3">ID камеры</th>
                <th className="px-4 py-3">Тип</th>
                <th className="px-4 py-3">Время</th>
                <th className="px-4 py-3">Снимок</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={4}>
                    Загрузка...
                  </td>
                </tr>
              ) : incidents.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={4}>
                    Инциденты не найдены
                  </td>
                </tr>
              ) : (
                incidents.map((incident) => {
                  const imageUrl = resolveImageUrl(incident.image_path);
                  return (
                    <tr key={incident.id} className="border-t border-slate-200">
                      <td className="px-4 py-3 font-medium text-ink">{incident.camera_id}</td>
                      <td className="px-4 py-3 text-slate-700">{incident.type}</td>
                      <td className="px-4 py-3 text-slate-600">{new Date(incident.timestamp).toLocaleString()}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          className="overflow-hidden rounded-lg border border-slate-300 transition hover:border-accent"
                          onClick={() => setPreviewImage(imageUrl)}
                        >
                          <img
                            src={imageUrl}
                            alt="Превью инцидента"
                            className="h-14 w-20 object-cover"
                            loading="lazy"
                          />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-2xl border border-white/60 bg-white/70 px-4 py-3">
        <p className="text-sm text-slate-600">
          Страница {page} из {totalPages} • всего {total}
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Назад
          </button>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Вперед
          </button>
        </div>
      </div>

      {previewImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/75 p-4" onClick={() => setPreviewImage(null)}>
          <div
            className="max-h-[90vh] max-w-5xl overflow-hidden rounded-2xl border border-white/30 bg-white"
            onClick={(event) => event.stopPropagation()}
          >
            <img src={previewImage} alt="Снимок инцидента" className="max-h-[80vh] w-full object-contain" />
            <div className="flex justify-end p-3">
              <button
                type="button"
                onClick={() => setPreviewImage(null)}
                className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}


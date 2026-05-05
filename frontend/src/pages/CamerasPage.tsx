import { FormEvent, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";

import { useAuth } from "../auth/AuthContext";
import { RoiCanvasEditor } from "../components/RoiCanvasEditor";
import { apiRequest } from "../lib/api";
import type { Camera, Zone } from "../types";

type CameraFormState = {
  name: string;
  rtsp_url: string;
  is_active: boolean;
};

const EMPTY_CAMERA_FORM: CameraFormState = {
  name: "",
  rtsp_url: "",
  is_active: true,
};

type CameraSnapshotResponse = {
  mime_type: string;
  image_base64: string;
};

export function CamerasPage() {
  const { accessToken } = useAuth();

  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(false);

  const [editingCameraId, setEditingCameraId] = useState<number | null>(null);
  const [cameraForm, setCameraForm] = useState<CameraFormState>(EMPTY_CAMERA_FORM);

  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [draftRoiPoints, setDraftRoiPoints] = useState<number[][]>([]);
  const [savingZone, setSavingZone] = useState(false);

  const selectedCameraZones = useMemo(
    () => zones.filter((zone) => (selectedCameraId ? zone.camera_id === selectedCameraId : true)),
    [selectedCameraId, zones],
  );

  const loadData = async (preferredCameraId?: number) => {
    if (!accessToken) {
      return;
    }
    setLoading(true);
    try {
      const [cameraList, zoneList] = await Promise.all([
        apiRequest<Camera[]>("/cameras", { token: accessToken }),
        apiRequest<Zone[]>("/zones", { token: accessToken }),
      ]);
      setCameras(cameraList);
      setZones(zoneList);

      if (cameraList.length === 0) {
        setSelectedCameraId(null);
      } else if (preferredCameraId && cameraList.some((camera) => camera.id === preferredCameraId)) {
        setSelectedCameraId(preferredCameraId);
      } else if (!selectedCameraId || !cameraList.some((camera) => camera.id === selectedCameraId)) {
        setSelectedCameraId(cameraList[0].id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось загрузить камеры и зоны";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const loadSnapshot = async (cameraId: number) => {
    if (!accessToken) {
      return;
    }

    setSnapshotLoading(true);
    try {
      const response = await apiRequest<CameraSnapshotResponse>(`/cameras/${cameraId}/snapshot`, {
        token: accessToken,
      });
      if (!response.image_base64) {
        setSnapshotUrl(null);
        toast.error("Снимок камеры пустой");
        return;
      }
      const mimeType = response.mime_type || "image/jpeg";
      setSnapshotUrl(`data:${mimeType};base64,${response.image_base64}`);
    } catch (error) {
      setSnapshotUrl(null);
      const message = error instanceof Error ? error.message : "Не удалось получить снимок";
      toast.error(message);
    } finally {
      setSnapshotLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useEffect(() => {
    if (!selectedCameraId) {
      setSnapshotUrl(null);
      setDraftRoiPoints([]);
      return;
    }
    setDraftRoiPoints([]);
    void loadSnapshot(selectedCameraId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCameraId, accessToken]);

  const resetCameraForm = () => {
    setEditingCameraId(null);
    setCameraForm(EMPTY_CAMERA_FORM);
  };

  const submitCameraForm = async (event: FormEvent) => {
    event.preventDefault();
    if (!accessToken) {
      return;
    }

    try {
      if (editingCameraId) {
        const updated = await apiRequest<Camera>(`/cameras/${editingCameraId}`, {
          method: "PUT",
          token: accessToken,
          body: cameraForm,
        });
        toast.success("Камера обновлена");
        await loadData(updated.id);
      } else {
        const created = await apiRequest<Camera>("/cameras", {
          method: "POST",
          token: accessToken,
          body: cameraForm,
        });
        toast.success("Камера создана");
        await loadData(created.id);
      }
      resetCameraForm();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка сохранения камеры";
      toast.error(message);
    }
  };

  const startEdit = (camera: Camera) => {
    setEditingCameraId(camera.id);
    setCameraForm({
      name: camera.name,
      rtsp_url: camera.rtsp_url,
      is_active: camera.is_active,
    });
  };

  const deleteCamera = async (cameraId: number) => {
    if (!accessToken) {
      return;
    }
    try {
      await apiRequest<void>(`/cameras/${cameraId}`, { method: "DELETE", token: accessToken });
      toast.success("Камера удалена");
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка удаления камеры";
      toast.error(message);
    }
  };

  const saveZoneFromCanvas = async () => {
    if (!accessToken || !selectedCameraId) {
      return;
    }
    if (draftRoiPoints.length < 3) {
      toast.error("Для зоны нужно минимум 3 точки");
      return;
    }

    setSavingZone(true);
    try {
      await apiRequest<Zone>("/zones", {
        method: "POST",
        token: accessToken,
        body: {
          camera_id: selectedCameraId,
          coordinates: draftRoiPoints,
        },
      });
      toast.success("ROI-зона сохранена");
      setDraftRoiPoints([]);
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка сохранения зоны";
      toast.error(message);
    } finally {
      setSavingZone(false);
    }
  };

  const deleteZone = async (zoneId: number) => {
    if (!accessToken) {
      return;
    }
    try {
      await apiRequest<void>(`/zones/${zoneId}`, { method: "DELETE", token: accessToken });
      toast.success("Зона удалена");
      await loadData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка удаления зоны";
      toast.error(message);
    }
  };

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-white/60 bg-white/80 p-6 shadow-panel">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink">Управление камерами</h1>
        <p className="mt-2 text-sm text-slate-600">Настройка камер и интерактивное создание ROI-зон по кликам.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-3xl border border-white/60 bg-white/85 p-5 shadow-panel">
          <h2 className="font-display text-xl font-semibold text-ink">{editingCameraId ? "Редактирование камеры" : "Новая камера"}</h2>
          <form onSubmit={submitCameraForm} className="mt-4 space-y-3">
            <input
              value={cameraForm.name}
              onChange={(event) => setCameraForm((prev) => ({ ...prev, name: event.target.value }))}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none ring-accent focus:border-accent focus:ring-2"
              placeholder="Название камеры"
              required
            />
            <input
              value={cameraForm.rtsp_url}
              onChange={(event) => setCameraForm((prev) => ({ ...prev, rtsp_url: event.target.value }))}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none ring-accent focus:border-accent focus:ring-2"
              placeholder="rtsp://..."
              required
            />
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={cameraForm.is_active}
                onChange={(event) => setCameraForm((prev) => ({ ...prev, is_active: event.target.checked }))}
              />
              Камера активна
            </label>
            <div className="flex gap-2">
              <button type="submit" className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white">
                {editingCameraId ? "Сохранить" : "Создать"}
              </button>
              {editingCameraId && (
                <button
                  type="button"
                  onClick={resetCameraForm}
                  className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
                >
                  Отмена
                </button>
              )}
            </div>
          </form>

          <div className="mt-6 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2">Название</th>
                  <th className="py-2">RTSP URL</th>
                  <th className="py-2">Статус</th>
                  <th className="py-2">Действия</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={4} className="py-4 text-slate-500">
                      Загрузка...
                    </td>
                  </tr>
                ) : cameras.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-4 text-slate-500">
                      Камеры не созданы
                    </td>
                  </tr>
                ) : (
                  cameras.map((camera) => (
                    <tr key={camera.id} className="border-t border-slate-200">
                      <td className="py-2 font-medium">{camera.name}</td>
                      <td className="max-w-[240px] truncate py-2 text-slate-600">{camera.rtsp_url}</td>
                      <td className="py-2">
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-semibold ${
                            camera.is_active ? "bg-accent/15 text-accent" : "bg-slate-200 text-slate-600"
                          }`}
                        >
                          {camera.is_active ? "активна" : "неактивна"}
                        </span>
                      </td>
                      <td className="space-x-2 py-2">
                        <button
                          type="button"
                          onClick={() => startEdit(camera)}
                          className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          onClick={() => void deleteCamera(camera.id)}
                          className="rounded-lg border border-rose-300 px-2 py-1 text-xs text-rose-700"
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-3xl border border-white/60 bg-white/85 p-5 shadow-panel">
          <h2 className="font-display text-xl font-semibold text-ink">ROI зоны</h2>
          <label className="mt-4 block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-slate-500">Камера</span>
            <select
              value={selectedCameraId ?? ""}
              disabled={cameras.length === 0}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                setSelectedCameraId(Number.isFinite(parsed) && parsed > 0 ? parsed : null);
              }}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none ring-accent focus:border-accent focus:ring-2"
            >
              {cameras.length === 0 ? (
                <option value="">Нет доступных камер</option>
              ) : (
                cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>
                    #{camera.id} {camera.name}
                  </option>
                ))
              )}
            </select>
          </label>
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              {snapshotLoading
                ? "Загружаем снимок камеры..."
                : snapshotUrl
                  ? "Снимок загружен. Нарисуйте полигон ROI по контуру рабочей зоны."
                  : "Снимок недоступен. Можно обновить или рисовать ROI поверх плейсхолдера."}
            </p>
            <button
              type="button"
              disabled={!selectedCameraId || snapshotLoading}
              onClick={() => selectedCameraId && void loadSnapshot(selectedCameraId)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Обновить снимок
            </button>
          </div>

          <div className="mt-4">
            <RoiCanvasEditor
              snapshotUrl={snapshotUrl}
              points={draftRoiPoints}
              existingZones={selectedCameraZones.map((zone) => zone.coordinates)}
              onAddPoint={(point) => setDraftRoiPoints((prev) => [...prev, point])}
              onClear={() => setDraftRoiPoints([])}
              onSave={() => void saveZoneFromCanvas()}
              saving={savingZone}
              disabled={!selectedCameraId}
            />
          </div>

          <div className="mt-6 space-y-2">
            {selectedCameraZones.length === 0 ? (
              <p className="text-sm text-slate-500">Для выбранной камеры зоны не найдены.</p>
            ) : (
              selectedCameraZones.map((zone) => (
                <div key={zone.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Зона #{zone.id}</p>
                    <button
                      type="button"
                      onClick={() => void deleteZone(zone.id)}
                      className="rounded-lg border border-rose-300 px-2 py-1 text-xs text-rose-700"
                    >
                      Удалить
                    </button>
                  </div>
                  <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                    {JSON.stringify(zone.coordinates)}
                  </pre>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

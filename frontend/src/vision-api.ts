export type Detection = {
  id: string
  track_id: number | null
  label: string
  confidence: number
  bbox: number[]
}
export type VideoFrame = {
  index: number
  source_frame: number
  time_s: number
  detections: Detection[]
  hazards: { category: string; severity: string; description: string }[]
  cues: { category: string; severity: string; description: string }[]
}
export type VisionJob = {
  id: string
  filename: string
  status: 'queued' | 'processing' | 'complete' | 'failed'
  progress_pct: number
  error: string | null
  frames: VideoFrame[]
  stats: null | {
    model: string
    device: string
    width: number
    height: number
    frames_analyzed: number
    source_frames_read: number
    duration_analyzed_s: number
    processing_s: number
    unique_tracked_objects: number
    hazard_observations: number
    visual_overlap_observations: number
    calibrated: boolean
    disclaimer: string
  }
}
export type VisionStatus = {
  available: boolean
  mode: string
  message: string
  model: string
  max_upload_mb: number
  max_frames: number
  frame_stride: number
  requires_calibration_for_metric_hazards: boolean
}

const base = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(base + path, { ...init, cache: 'no-store' })
  if (!res.ok) {
    let message = `Request failed (HTTP ${res.status})`
    try {
      const data = await res.json()
      if (data.detail) message = String(data.detail)
    } catch { /* No JSON body */ }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const getVisionStatus = () => request<VisionStatus>('/api/vision/status')
export const getVisionJob = (id: string) => request<VisionJob>(`/api/vision/jobs/${encodeURIComponent(id)}`)
export const getFrameURL = (id: string, index: number) =>
  `${base}/api/vision/jobs/${encodeURIComponent(id)}/frames/${index}`

export function submitVideo(file: File, calibration: string): Promise<VisionJob> {
  const body = new FormData()
  body.append('file', file)
  if (calibration.trim()) body.append('calibration', calibration)
  return request<VisionJob>('/api/vision/jobs', { method: 'POST', body })
}

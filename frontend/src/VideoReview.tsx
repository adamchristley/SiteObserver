import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, ArrowRight, Camera, CheckCircle2, ChevronLeft, ChevronRight,
  CircleDot, Clapperboard, Clock3, CloudOff, FileVideo, Gauge, Info,
  Loader2, Pause, Play, RotateCcw, ScanSearch, Shield, UploadCloud, Users, X,
} from 'lucide-react'
import { getFrameURL, getVisionJob, getVisionStatus, submitVideo } from './vision-api'
import type { VisionJob, VisionStatus } from './vision-api'
import './vision.css'

const exampleCalibration = JSON.stringify({
  pixel_points: [[100, 100], [800, 100], [800, 500], [100, 500]],
  world_points: [[0, 0], [20, 0], [20, 12], [0, 12]],
}, null, 2)

function formatSeconds(value: number) {
  return value.toFixed(1) + 's'
}
function Stat({ label, value, note }: { label: string; value: number | string; note: string }) {
  return <div className="vision-stat"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
}

export default function VideoReview() {
  const [availability, setAvailability] = useState<VisionStatus | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [calibration, setCalibration] = useState('')
  const [job, setJob] = useState<VisionJob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getVisionStatus().then(setAvailability).catch(e => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!job || job.status === 'complete' || job.status === 'failed') return
    let cancelled = false
    const timer = window.setInterval(async () => {
      try {
        const updated = await getVisionJob(job.id)
        if (!cancelled) setJob(updated)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not update job')
      }
    }, 1300)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [job?.id, job?.status])

  useEffect(() => {
    if (!playing || !job?.frames.length) return
    const timer = window.setInterval(() => {
      setFrameIndex(old => {
        if (old >= job.frames.length - 1) {
          if (job.status === 'complete') {
            setPlaying(false)
            return 0
          }
          return old
        }
        return old + 1
      })
    }, 450)
    return () => window.clearInterval(timer)
  }, [playing, job?.frames.length, job?.status])

  const frame = job?.frames[Math.min(frameIndex, Math.max(0, job.frames.length - 1))]
  const totals = useMemo(() => {
    const frames = job?.frames || []
    return {
      people: frames.reduce((n, f) => n + f.detections.filter(d => d.label === 'person').length, 0),
      equipment: frames.reduce((n, f) => n + f.detections.filter(d => d.label !== 'person').length, 0),
      cues: frames.reduce((n, f) => n + f.cues.length, 0),
    }
  }, [job?.frames])

  async function start() {
    if (!selectedFile || uploading) return
    if (selectedFile.size > 80 * 1024 * 1024) {
      setError('Please select a video smaller than 80 MB.')
      return
    }
    setError(null)
    setUploading(true)
    try {
      const next = await submitVideo(selectedFile, calibration)
      setJob(next)
      setFrameIndex(0)
      setPlaying(false)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="vision-layout">
      <div className="vision-banner">
        <div className="vision-banner-icon"><ScanSearch size={23} /></div>
        <div><strong>Computer vision laboratory</strong><p>Analyze local footage with YOLO11 + ByteTrack. Results are generated on your computer, not in Azure.</p></div>
        <span className="vision-mode">LOCAL INFERENCE</span>
      </div>

      {!availability?.available && (
        <div className="vision-setup">
          <div><CloudOff size={20} /><strong>Optional vision service is not active</strong></div>
          <p>The dashboard and simulator still work. To enable YOLO inference, stop your current Compose session and restart with the vision configuration:</p>
          <code>docker compose -f compose.yaml -f compose.vision.yaml up --build</code>
          <p>This installs free, open-source inference packages locally. The first analysis downloads YOLO model weights. No cloud services or payment information are used.</p>
          <button onClick={() => { setError(null); getVisionStatus().then(setAvailability).catch(e => setError(String(e))) }}><RotateCcw size={14}/> Check again</button>
        </div>
      )}

      <div className="vision-columns">
        <section className="panel vision-upload">
          <div className="panel-head"><div><span className="section-kicker">INPUT SOURCE</span><h2>Video analysis</h2></div><Camera size={20} className="vision-muted-icon"/></div>
          <input
            type="file"
            ref={picker}
            accept=".mp4,.mov,.avi,.mkv,.webm,video/*"
            className="vision-hidden-input"
            onChange={event => { setSelectedFile(event.target.files?.[0] || null); setError(null) }}
          />
          <button className="vision-drop" onClick={() => picker.current?.click()}>
            <span className="vision-upload-circle"><UploadCloud size={25}/></span>
            <strong>{selectedFile ? selectedFile.name : 'Choose construction-site footage'}</strong>
            <span>{selectedFile ? `${(selectedFile.size / 1048576).toFixed(1)} MB · Click to replace` : 'MP4 recommended · Maximum 80 MB'}</span>
          </button>
          <div className="vision-upload-note"><Info size={15}/><span>Use videos you have the right to process. Uploads stay on this local machine and are deleted after analysis; temporary preview frames remain until the service restarts or old jobs are cleared.</span></div>

          <details className="vision-calibration">
            <summary><Gauge size={17}/> Optional camera calibration <span>ADVANCED</span></summary>
            <p>To enable approximate meter-based hazard calculations, provide four corresponding ground-plane points in pixel and world coordinates, in matching order. Use a stationary camera and measured points. Example values below are illustrative and must not be used for a real camera.</p>
            <textarea
              spellCheck={false} rows={6} value={calibration}
              placeholder={exampleCalibration}
              onChange={event => setCalibration(event.target.value)}
              aria-label="Four-point camera calibration JSON"
            />
          </details>
          <button className="vision-run" disabled={!selectedFile || !availability?.available || uploading || (job?.status === 'processing' || job?.status === 'queued')} onClick={() => { void start() }}>
            {uploading ? <Loader2 size={17} className="vision-spin"/> : <Play size={17} fill="currentColor"/>}
            {uploading ? 'Uploading...' : 'Analyze video'} <ArrowRight size={17}/>
          </button>
          {error && <div className="vision-error"><AlertCircle size={17}/><span>{error}</span><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={15}/></button></div>}
        </section>

        <section className="panel vision-preview">
          <div className="panel-head"><div><span className="section-kicker">DETECTION FEED</span><h2>Tracked objects</h2></div><span className={`vision-state ${job?.status || 'idle'}`}><CircleDot size={13}/>{job?.status.toUpperCase() || 'AWAITING INPUT'}</span></div>
          {frame ? (
            <div className="vision-player">
              <img src={getFrameURL(job!.id, frame.index)} alt={`Annotated frame ${frame.index + 1} showing detected objects and bounding boxes`} />
              <div className="vision-video-tag"><span className="signal-dot"/> YOLO11 · BYTETRACK</div>
              <div className="vision-video-time">{formatSeconds(frame.time_s)}</div>
            </div>
          ) : (
            <div className="vision-placeholder"><Clapperboard size={39} strokeWidth={1.2}/><strong>No footage analyzed yet</strong><p>Your annotated frames, tracking IDs, and visual observations will appear here.</p></div>
          )}
          <div className="vision-controls">
            <button disabled={!frame} onClick={() => setFrameIndex(i => Math.max(0, i - 1))} aria-label="Previous frame"><ChevronLeft size={18}/></button>
            <button disabled={!frame} onClick={() => setPlaying(p => !p)} aria-label={playing ? 'Pause playback' : 'Play frames'}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button>
            <button disabled={!frame} onClick={() => setFrameIndex(i => Math.min((job?.frames.length || 1) - 1, i + 1))} aria-label="Next frame"><ChevronRight size={18}/></button>
            <input
              type="range" min={0} max={Math.max(0, (job?.frames.length || 1) - 1)}
              value={Math.min(frameIndex, Math.max(0, (job?.frames.length || 1) - 1))}
              disabled={!frame}
              onChange={event => { setPlaying(false); setFrameIndex(Number(event.target.value)) }}
              aria-label="Seek analyzed frames"
            />
            <span>{frame ? `${frame.index + 1}/${job?.frames.length}` : '0/0'}</span>
          </div>
          <div className="vision-player-note"><Info size={15}/><span>Playback shows sampled, annotated frames, not the original video's real-time frame rate.</span></div>
        </section>
      </div>

      {job && (
        <section className="panel vision-results">
          <div className="panel-head"><div><span className="section-kicker">MODEL OUTPUT</span><h2>Analysis report</h2></div><span className="vision-file"><FileVideo size={15}/>{job.filename}</span></div>
          {(job.status === 'queued' || job.status === 'processing') && <div className="vision-progress"><div><Loader2 size={16} className="vision-spin"/> Processing locally. CPU analysis may take several minutes.</div><div className="vision-progress-rail"><span style={{width: `${job.progress_pct}%`}}/></div><small>{job.frames.length} sampled frames complete</small></div>}
          {job.status === 'failed' && <div className="vision-error"><AlertCircle size={17}/>{job.error}</div>}
          {job.status === 'complete' && <div className="vision-done"><CheckCircle2 size={17}/> Analysis complete in {job.stats?.processing_s}s. Model: {job.stats?.model}.</div>}
          <div className="vision-stats">
            <Stat label="Analyzed frames" value={job.frames.length} note="Every fourth source frame"/>
            <Stat label="Person detections" value={totals.people} note="Frame observations, not unique people"/>
            <Stat label="Vehicle detections" value={totals.equipment} note="COCO road vehicle categories"/>
            <Stat label={job.stats?.calibrated ? 'Metric hazard cues' : 'Visual overlap cues'} value={job.stats?.calibrated ? job.stats.hazard_observations : totals.cues} note={job.stats?.calibrated ? 'Unvalidated calibrated estimates' : 'Not physical-distance estimates'}/>
          </div>
          <div className="vision-inference-notice"><Shield size={17}/>{job.stats?.disclaimer || (calibration.trim() ? 'Calibration provided. Interpret geometric estimates cautiously.' : 'No calibration supplied. Image overlap is not a real-world hazard or collision measurement.')}</div>
          {frame && <div className="vision-frame-details">
            <div><span className="section-kicker">CURRENT FRAME</span><h3>Frame {frame.index + 1} <small>· {formatSeconds(frame.time_s)}</small></h3></div>
            {frame.detections.length ? <div className="vision-detection-list">{frame.detections.map((d, i) => (
              <div key={d.id + i}><span className={d.label === 'person' ? 'vision-type-person' : 'vision-type-vehicle'}><Users size={13}/>{d.label}</span><strong>{d.id}</strong><small>{Math.round(d.confidence * 100)}% confidence</small></div>
            ))}</div> : <p className="vision-muted">No supported COCO classes detected in this frame.</p>}
            {[...frame.cues, ...frame.hazards].length > 0 && <div className="vision-frame-cues">{[...frame.cues, ...frame.hazards].map((cue, i) => <div key={i}><AlertCircle size={15}/>{cue.description}</div>)}</div>}
          </div>}
        </section>
      )}
      <div className="vision-caution"><Clock3 size={15}/> The bundled pretrained COCO detector recognizes people and common road vehicles. Excavators, forklifts, hardhats, and construction-specific classes require separate fine-tuning. Do not treat this research prototype as a live safety alarm.</div>
    </div>
  )
}

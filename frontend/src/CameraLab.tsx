import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Camera, CircleDot, Play, Square, UserRound, Video } from 'lucide-react'
import { analyzeCameraFrame } from './vision-api'
import type { CameraSample } from './vision-api'
import './camera.css'

export default function CameraLab({ enabled }: { enabled: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const sessionId = useRef(crypto.randomUUID())
  const intervalRef = useRef<number | null>(null)
  const inFlight = useRef(false)
  const active = useRef(false)
  const [running, setRunning] = useState(false)
  const [sample, setSample] = useState<CameraSample | null>(null)
  const [sampleCount, setSampleCount] = useState(0)
  const [error, setError] = useState<string | null>(null)

  function stopCamera() {
    active.current = false
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setRunning(false)
  }

  useEffect(() => {
    return () => {
      active.current = false
      if (intervalRef.current !== null) window.clearInterval(intervalRef.current)
      streamRef.current?.getTracks().forEach(t => t.stop())
    }
  }, [])

  async function capture() {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas || !active.current || inFlight.current || !video.videoWidth) return
    inFlight.current = true
    try {
      const width = Math.min(640, video.videoWidth)
      const height = Math.round(width * video.videoHeight / video.videoWidth)
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Camera canvas not available')
      ctx.drawImage(video, 0, 0, width, height)
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.78))
      if (!blob) throw new Error('Could not capture a JPEG')
      const next = await analyzeCameraFrame(blob, sessionId.current)
      if (active.current) {
        setSample(next)
        setSampleCount(count => count + 1)
        setError(null)
      }
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : String(failure))
    } finally {
      inFlight.current = false
    }
  }

  async function startCamera() {
    if (!enabled) return
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser does not support camera access on this page.')
      return
    }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { width: { ideal: 640 }, height: { ideal: 360 }, facingMode: 'environment' },
      })
      streamRef.current = stream
      sessionId.current = crypto.randomUUID()
      setSample(null)
      setSampleCount(0)
      if (!videoRef.current) {
        stream.getTracks().forEach(t => t.stop())
        return
      }
      videoRef.current.srcObject = stream
      await videoRef.current.play()
      active.current = true
      setRunning(true)
      void capture()
      intervalRef.current = window.setInterval(() => { void capture() }, 2000)
    } catch (failure) {
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
      setError(failure instanceof Error ? failure.message : 'Could not start camera')
    }
  }

  const people = sample?.detections.filter(d => d.label === 'person').length || 0
  const vehicles = sample?.detections.filter(d => d.label !== 'person').length || 0
  return (
    <section className="panel camera-lab">
      <div className="panel-head">
        <div><span className="section-kicker">EXPERIMENTAL · SAMPLED WEBCAM</span><h2>Camera monitor</h2></div>
        <span className="camera-status"><CircleDot size={12}/>{running ? 'CAMERA ACTIVE' : 'CAMERA OFF'}</span>
      </div>
      <div className="camera-help">Enable webcam access to compare the original feed with sampled YOLO + ByteTrack detections. Frames stay in memory and are not stored or sent to Azure.</div>
      <div className="camera-grid">
        <div className="camera-view">
          <div className="camera-view-label"><Camera size={14}/> LOCAL CAMERA</div>
          <video ref={videoRef} playsInline muted autoPlay className="camera-video"/>
          {!running && <div className="camera-blank"><Video size={27}/><span>Camera not started</span></div>}
        </div>
        <div className="camera-view">
          <div className="camera-view-label"><UserRound size={14}/> AI ANNOTATED SAMPLE</div>
          {sample ? (
            <img src={`data:image/jpeg;base64,${sample.image_base64}`} alt="Latest sampled frame with YOLO detection boxes" className="camera-video" />
          ) : <div className="camera-blank"><Camera size={28}/><span>Waiting for detections</span></div>}
        </div>
      </div>
      <canvas ref={canvasRef} className="camera-hidden"/>
      <div className="camera-toolbar">
        <button className="camera-action" disabled={!enabled} onClick={() => { if (running) stopCamera(); else void startCamera() }}>
          {running ? <Square size={15} fill="currentColor"/> : <Play size={16} fill="currentColor"/>}
          {running ? 'Stop camera' : 'Start camera'}
        </button>
        <span>{sampleCount} frames analyzed</span>
        <span>{people} people · {vehicles} vehicles detected</span>
        {inFlight.current && <span>Processing</span>}
      </div>
      {error && <div className="camera-error"><AlertCircle size={16}/>{error}</div>}
      <div className="camera-disclaimer">The browser samples approximately every two seconds, with slower updates if CPU inference is busy. Detection boxes are observational only, not calibrated hazard alarms. Supports one active camera tracking session per backend process.</div>
    </section>
  )
}

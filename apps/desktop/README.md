# AK Virtual Camera — Desktop App

PySide6 desktop application; MVVM.

```
python -m akvc_app
```

The app spawns a `FrameWorker` subprocess that owns the Frame Bus producer
(`akvc.core.frame_sink.windows_shm.WindowsShmSink`) and streams the configured
source through the pipeline.

The DirectShow filter (loaded into OBS / Zoom / Chrome / WeChat / etc.) is the
consumer end; it discovers the frame bus by name and reads NV12 frames.

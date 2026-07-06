from __future__ import annotations

import signal
import time

from akvc_app.services.facade import ServiceFacade

running = True


def _stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

facade = ServiceFacade()
facade.bootstrap()
facade.select_source("test:checkerboard")
facade.start()

try:
    while running:
        st = facade.poll_status()
        print(
            f"running={st.running} fps={st.fps:.2f} "
            f"published={st.frames_published} dropped={st.frames_dropped} consumers={st.consumer_count}",
            flush=True,
        )
        time.sleep(1.0)
finally:
    facade.stop()
    facade.shutdown()

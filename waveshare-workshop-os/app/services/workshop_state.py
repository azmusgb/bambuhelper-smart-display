"""Workshop OS state model foundation."""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class WorkshopState:
    device: str = "ws_lcd_350"
    release: str = "v8"
    status: str = "online"
    active_view: str = "home"
    updated_at: str = ""

    def refresh_timestamp(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        self.refresh_timestamp()
        return asdict(self)

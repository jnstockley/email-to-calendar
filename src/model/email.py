from dataclasses import dataclass
from datetime import datetime


@dataclass
class EMail:
    id: int
    subject: str
    from_address: str
    delivery_date: datetime
    body: str

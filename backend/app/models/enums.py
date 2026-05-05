from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"


class IncidentType(str, Enum):
    sleep = "sleep"
    absence = "absence"
    phone = "phone"
    smoking = "smoking"
    anomalous_movement = "anomalous_movement"

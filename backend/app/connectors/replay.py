import os
import csv
from app.connectors.base import BaseConnector

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_SOURCE = os.path.join(CURRENT_DIR, "mock_live_feed.csv")
POINTER_FILE = os.path.join(CURRENT_DIR, "replay_pointer.txt")

class ReplayConnector(BaseConnector):
    def __init__(self, channel: str):
        self.channel = channel

    def _get_last_index(self) -> int:
        if not os.path.exists(POINTER_FILE):
            return 0
        with open(POINTER_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0

    def _save_last_index(self, index: int):
        with open(POINTER_FILE, "w") as f:
            f.write(str(index))

    def fetch(self) -> list[dict]:
        if not os.path.exists(CSV_SOURCE):
            return []

        last_index = self._get_last_index()
        raw_rows = []
        
        with open(CSV_SOURCE, mode="r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            if not reader:
                return []
            
            # Reset index to 0 if we reached the end of the CSV to cycle infinitely
            if last_index >= len(reader):
                last_index = 0
                self._save_last_index(0)
            
            # Find the next row matching this connector's channel starting from the last index
            for idx in range(last_index, len(reader)):
                row = reader[idx]
                if row.get("channel") == self.channel:
                    raw_rows.append({"index": idx + 1, "data": row})
                    break
            
            # If nothing found but we had a non-zero index, reset to 0 and search from beginning
            if not raw_rows and last_index > 0:
                last_index = 0
                self._save_last_index(0)
                for idx in range(0, len(reader)):
                    row = reader[idx]
                    if row.get("channel") == self.channel:
                        raw_rows.append({"index": idx + 1, "data": row})
                        break
        
        return raw_rows

    def normalize(self, raw: dict) -> dict:
        data = raw["data"]
        # Save index pointer so we don't replay the same row next run
        self._save_last_index(raw["index"])

        payload = {
            "raw_text": data.get("complaint_text") or "",
            "customer_id": data.get("customer_id") or None,
            "source_ref": f"replay-{raw['index']}",
            "channel_metadata": {
                "branch_code": data.get("branch_code") or "N/A",
                "agent_name": data.get("agent_name") or "N/A",
                "ivr_duration_sec": data.get("duration") or "N/A"
            }
        }

        media_file = data.get("media_file")
        media_type = data.get("media_type")
        if media_file and media_type:
            filepath = os.path.join(CURRENT_DIR, media_file)
            if os.path.exists(filepath):
                try:
                    import base64
                    with open(filepath, "rb") as f:
                        file_bytes = f.read()
                        base64_str = base64.b64encode(file_bytes).decode('utf-8')
                        payload["media_file"] = f"data:{media_type};base64,{base64_str}"
                        payload["media_type"] = media_type
                except Exception as e:
                    print(f"Error encoding replay connector attachment: {e}")

        return payload

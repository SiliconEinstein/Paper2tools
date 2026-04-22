"""TOS 同步管理器 - Lance 数据库与 TOS 的增量同步（快照对比机制）"""

from pathlib import Path
from typing import Dict, Set, Tuple


class LanceTosSync:
    """Lance 数据库与 TOS 的增量同步。基于文件 (size, mtime_ns) 快照检测变更。"""

    def __init__(self, local_db_path: Path, tos_client, bucket: str, tos_prefix: str):
        self.local_db_path = local_db_path
        self.tos_client = tos_client
        self.bucket = bucket
        self.tos_prefix = tos_prefix.rstrip('/') + '/'
        self._snapshot: Dict[str, Tuple[int, int]] = {}

    def download_from_tos(self, force: bool = False) -> None:
        """从 TOS 下载数据库到本地。force=True 强制重新下载。"""
        if self.local_db_path.exists() and not force:
            if any(self.local_db_path.iterdir()):
                print(f"Local database already exists: {self.local_db_path}, use force=True to re-download")
                self._snapshot = self._snapshot_local_files()
                return

        self.local_db_path.mkdir(parents=True, exist_ok=True)

        try:
            marker = ""
            file_count = 0
            while True:
                resp = self.tos_client.list_objects_type2(
                    bucket=self.bucket, prefix=self.tos_prefix,
                    marker=marker, max_keys=1000
                )
                if not resp.contents:
                    break

                for obj in resp.contents:
                    relative_path = obj.key[len(self.tos_prefix):]
                    if not relative_path:
                        continue
                    local_file = self.local_db_path / relative_path
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    self.tos_client.get_object_to_file(
                        bucket=self.bucket, key=obj.key, file_path=str(local_file)
                    )
                    file_count += 1

                if not resp.is_truncated:
                    break
                marker = resp.next_marker

            print(f"Downloaded {file_count} files from TOS: {self.tos_prefix}")
        except Exception as e:
            print(f"Error downloading from TOS: {e}")
            raise

        self._snapshot = self._snapshot_local_files()

    def upload_to_tos(self, incremental: bool = True) -> None:
        """上传本地数据库到 TOS。incremental=True 只上传变更文件。"""
        if not self.local_db_path.exists():
            print(f"Local database does not exist: {self.local_db_path}")
            return

        current_snapshot = self._snapshot_local_files()
        if incremental:
            changed_files = self._get_changed_files(current_snapshot)
        else:
            changed_files = set(current_snapshot.keys())

        if not changed_files:
            print("No files changed, skip upload")
            return

        try:
            for relative_path in changed_files:
                local_file = self.local_db_path / relative_path
                tos_key = self.tos_prefix + relative_path
                self.tos_client.put_object_from_file(
                    bucket=self.bucket, key=tos_key, file_path=str(local_file)
                )
            print(f"Uploaded {len(changed_files)} files to TOS: {self.tos_prefix}")
        except Exception as e:
            print(f"Error uploading to TOS: {e}")
            raise

        self._snapshot = current_snapshot

    def _snapshot_local_files(self) -> Dict[str, Tuple[int, int]]:
        """记录本地文件快照 {relative_path: (size, mtime_ns)}。"""
        snapshot = {}
        if not self.local_db_path.exists():
            return snapshot
        for file_path in self.local_db_path.rglob('*'):
            if file_path.is_file():
                rel = str(file_path.relative_to(self.local_db_path))
                stat = file_path.stat()
                snapshot[rel] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    def _get_changed_files(self, current: Dict[str, Tuple[int, int]]) -> Set[str]:
        """对比快照，返回变更文件集合。"""
        changed = set()
        for path, (size, mtime) in current.items():
            if path not in self._snapshot:
                changed.add(path)
            else:
                old_size, old_mtime = self._snapshot[path]
                if size != old_size or mtime != old_mtime:
                    changed.add(path)
        return changed

    def get_sync_stats(self) -> Dict[str, int]:
        return {
            "total_files": len(self._snapshot),
            "total_size": sum(size for size, _ in self._snapshot.values()),
        }

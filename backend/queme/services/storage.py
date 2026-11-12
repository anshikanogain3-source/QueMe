from io import BytesIO
import mimetypes
from pathlib import Path

from flask import current_app, send_file


class Storage:
    def put(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def send(self, key: str, download_name: str = "answer.webm"):
        raise NotImplementedError

    def delete(self, key: str):
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        root = self.root.resolve()
        path = (root / key).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError("Invalid storage key")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        self._path(key).write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def send(self, key: str, download_name: str = "answer.webm"):
        content_type = mimetypes.guess_type(key)[0] or "audio/webm"
        return send_file(self._path(key), mimetype=content_type, download_name=download_name)

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)


class R2Storage(Storage):
    def __init__(self, app):
        import boto3

        account = app.config["R2_ACCOUNT_ID"]
        self.bucket = app.config["R2_BUCKET_NAME"]
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=app.config["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=app.config["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    def put(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def send(self, key: str, download_name: str = "answer.webm"):
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        content_type = obj.get("ContentType") or mimetypes.guess_type(key)[0] or "audio/webm"
        return send_file(BytesIO(obj["Body"].read()), mimetype=content_type, download_name=download_name, as_attachment=False)

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)


class S3Storage(Storage):
    """Private AWS or S3-compatible bucket storage using boto3's credential chain."""

    def __init__(self, app):
        import boto3
        from botocore.config import Config

        self.bucket = app.config["S3_BUCKET_NAME"]
        options = {"addressing_style": app.config.get("S3_ADDRESSING_STYLE", "auto")}
        client_options = {
            "region_name": app.config.get("S3_REGION") or "us-east-1",
            "endpoint_url": app.config.get("S3_ENDPOINT_URL") or None,
            "config": Config(s3=options),
        }
        access_key = app.config.get("AWS_ACCESS_KEY_ID")
        secret_key = app.config.get("AWS_SECRET_ACCESS_KEY")
        if access_key and secret_key:
            client_options.update(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        self.client = boto3.client("s3", **client_options)

    def put(self, key: str, data: bytes, content_type: str = "audio/webm") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            return response["Body"].read()
        finally:
            response["Body"].close()

    def send(self, key: str, download_name: str = "answer.webm"):
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        stream = response["Body"]
        try:
            body = stream.read()
        finally:
            stream.close()
        content_type = response.get("ContentType") or mimetypes.guess_type(key)[0] or "audio/webm"
        return send_file(BytesIO(body), mimetype=content_type, download_name=download_name, as_attachment=False)

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> Storage:
    backend = current_app.config.get("STORAGE_BACKEND", "local")
    if backend == "r2" and current_app.config.get("R2_ACCOUNT_ID"):
        return R2Storage(current_app)
    if backend == "s3":
        return S3Storage(current_app)
    return LocalStorage(current_app.config["STORAGE_LOCAL_DIR"])

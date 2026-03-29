# AWS S3

Manage AWS S3 buckets and objects — list buckets, list objects, and upload files.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: aws, s3, bucket, cloud storage, amazon

## System Prompt
You can use AWS S3. Credentials must be configured via `steelclaw skills configure aws_s3`.

## Tools

### list_buckets
List all S3 buckets in the account.

**Parameters:**
(none)

### list_objects
List objects in an S3 bucket.

**Parameters:**
- `bucket` (string, required): Bucket name
- `prefix` (string): Key prefix to filter results
- `max_keys` (integer): Maximum objects to return (default: 50)

### upload_file
Upload a local file to an S3 bucket.

**Parameters:**
- `local_path` (string, required): Local file path
- `bucket` (string, required): Destination bucket name
- `key` (string, required): Destination object key

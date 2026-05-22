#!/bin/bash
# Upload a chart image to a Slack channel (or thread)
# Usage: ./upload_chart.sh <file_path> <channel_id> <title> [comment] [thread_ts]
#
# Requires: $SLACK_BOT_TOKEN

FILE_PATH="$1"
CHANNEL_ID="$2"
TITLE="$3"
COMMENT="${4:-}"
THREAD_TS="${5:-}"

if [ -z "$FILE_PATH" ] || [ -z "$CHANNEL_ID" ] || [ -z "$TITLE" ]; then
    echo "Usage: ./upload_chart.sh <file_path> <channel_id> <title> [comment] [thread_ts]"
    exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
    echo "File not found: $FILE_PATH"
    exit 1
fi

FILESIZE=$(stat -c%s "$FILE_PATH")
FILENAME=$(basename "$FILE_PATH")

# Step 1: Get upload URL
UPLOAD_RESP=$(curl -s -X POST "https://slack.com/api/files.getUploadURLExternal" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "filename=$FILENAME&length=$FILESIZE")

UPLOAD_URL=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('upload_url',''))")
FILE_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('file_id',''))")

if [ -z "$UPLOAD_URL" ] || [ -z "$FILE_ID" ]; then
    echo "Failed to get upload URL"
    echo "$UPLOAD_RESP"
    exit 1
fi

# Step 2: Upload file
curl -s -X POST "$UPLOAD_URL" -F "file=@$FILE_PATH" > /dev/null

# Step 3: Complete upload and share
COMPLETE_BODY="{\"files\":[{\"id\":\"$FILE_ID\",\"title\":\"$TITLE\"}],\"channel_id\":\"$CHANNEL_ID\""
if [ -n "$THREAD_TS" ]; then
    COMPLETE_BODY="$COMPLETE_BODY,\"thread_ts\":\"$THREAD_TS\""
fi
if [ -n "$COMMENT" ]; then
    # Escape quotes in comment
    ESCAPED_COMMENT=$(echo "$COMMENT" | sed 's/"/\\"/g')
    COMPLETE_BODY="$COMPLETE_BODY,\"initial_comment\":\"$ESCAPED_COMMENT\""
fi
COMPLETE_BODY="$COMPLETE_BODY}"

RESULT=$(curl -s -X POST "https://slack.com/api/files.completeUploadExternal" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$COMPLETE_BODY")

OK=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))")

if [ "$OK" = "True" ]; then
    echo "Chart uploaded: $TITLE → $CHANNEL_ID"
else
    echo "Upload failed:"
    echo "$RESULT"
    exit 1
fi

#!/bin/bash
# Download GroundingDINO weights into the naturalnav_weights volume.
# Run once after the first `docker compose up`.
set -e

VARIANT="${1:-swint_ogc}"

case "$VARIANT" in
  swint_ogc)
    URL="https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth"
    FILE="groundingdino_swint_ogc.pth"
    ;;
  swinb_cogcoor)
    URL="https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha2/groundingdino_swinb_cogcoor.pth"
    FILE="groundingdino_swinb_cogcoor.pth"
    ;;
  *)
    echo "Unknown variant: $VARIANT (use swint_ogc or swinb_cogcoor)" >&2
    exit 1
    ;;
esac

echo "Downloading $FILE into naturalnav_weights volume..."
docker compose run --rm naturalnav bash -c "
  mkdir -p /root/.cache/naturalnav/groundingdino
  cd /root/.cache/naturalnav/groundingdino
  if [ -f '$FILE' ]; then
    echo 'Already present: '\$(du -h '$FILE' | cut -f1)
  else
    curl -L -o '$FILE' '$URL'
    echo 'Downloaded: '\$(du -h '$FILE' | cut -f1)
  fi
"

import * as pdfjs from "./vendor/pdfjs@4.10.38/pdf.min.mjs";

const WORKER_URL = new URL("./vendor/pdfjs@4.10.38/pdf.worker.min.mjs", import.meta.url).href;
const MINIMUM_REGION_AREA = 9_000;
const MAXIMUM_REGIONS_PER_PAGE = 8;

pdfjs.GlobalWorkerOptions.workerSrc = WORKER_URL;

function pageBounds(viewport) {
  return { left: 0, top: 0, right: viewport.width, bottom: viewport.height };
}

function normalizedBounds(rectangle) {
  const [firstX, firstY, secondX, secondY] = rectangle;
  return {
    left: Math.min(firstX, secondX),
    top: Math.min(firstY, secondY),
    right: Math.max(firstX, secondX),
    bottom: Math.max(firstY, secondY),
  };
}

function area(bounds) {
  return Math.max(0, bounds.right - bounds.left) * Math.max(0, bounds.bottom - bounds.top);
}

function intersecting(left, right) {
  return !(
    left.right < right.left || right.right < left.left || left.bottom < right.top || right.bottom < left.top
  );
}

function mergeBounds(left, right) {
  return {
    left: Math.min(left.left, right.left),
    top: Math.min(left.top, right.top),
    right: Math.max(left.right, right.right),
    bottom: Math.max(left.bottom, right.bottom),
  };
}

function pathBounds(operatorList, viewport) {
  const candidates = [];
  for (let index = 0; index < operatorList.fnArray.length; index += 1) {
    if (operatorList.fnArray[index] !== pdfjs.OPS.constructPath) {
      continue;
    }
    const args = operatorList.argsArray[index];
    const minMax = Array.isArray(args) ? args.at(-1) : null;
    if (!Array.isArray(minMax) || minMax.length !== 4) {
      continue;
    }
    const candidate = normalizedBounds(viewport.convertToViewportRectangle(minMax));
    const fullPage = area(pageBounds(viewport));
    if (area(candidate) > fullPage * 0.8) {
      continue;
    }
    candidates.push(candidate);
  }
  // A chart is often made of individually-small bars. Merge all connected
  // path bounds before filtering by area so a valid figure is not discarded.
  const regions = [];
  for (const candidate of candidates) {
    let merged = candidate;
    let matched = true;
    while (matched) {
      matched = false;
      for (let index = regions.length - 1; index >= 0; index -= 1) {
        if (intersecting(regions[index], merged)) {
          merged = mergeBounds(regions[index], merged);
          regions.splice(index, 1);
          matched = true;
        }
      }
    }
    regions.push(merged);
  }
  return regions
    .filter((region) => area(region) >= MINIMUM_REGION_AREA)
    .sort((left, right) => area(right) - area(left))
    .slice(0, MAXIMUM_REGIONS_PER_PAGE);
}

async function pngBytes(canvas) {
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((result) => (result ? resolve(result) : reject(new Error("PNG encoding failed"))), "image/png");
  });
  return new Uint8Array(await blob.arrayBuffer());
}

async function renderRegion(page, viewport, bounds) {
  const scale = 1.5;
  const fullCanvas = document.createElement("canvas");
  fullCanvas.width = Math.ceil(viewport.width * scale);
  fullCanvas.height = Math.ceil(viewport.height * scale);
  const fullContext = fullCanvas.getContext("2d", { alpha: false });
  if (!fullContext) {
    throw new Error("Canvas 2D context unavailable");
  }
  await page.render({ canvasContext: fullContext, viewport: page.getViewport({ scale }) }).promise;

  const width = Math.ceil((bounds.right - bounds.left) * scale);
  const height = Math.ceil((bounds.bottom - bounds.top) * scale);
  const crop = document.createElement("canvas");
  crop.width = width;
  crop.height = height;
  const cropContext = crop.getContext("2d", { alpha: false });
  if (!cropContext) {
    throw new Error("Crop canvas 2D context unavailable");
  }
  cropContext.drawImage(
    fullCanvas,
    Math.floor(bounds.left * scale),
    Math.floor(bounds.top * scale),
    width,
    height,
    0,
    0,
    width,
    height,
  );
  return { bytes: await pngBytes(crop), width, height };
}

function isPdf(file) {
  return file.mime === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

/**
 * Render meaningful vector-path regions locally. The returned byte arrays are
 * deliberately kept in the browser and never uploaded or sent to a service.
 */
export async function renderVectorFigures(files) {
  const artifacts = [];
  const failures = [];
  for (const file of files.filter(isPdf)) {
    let document;
    try {
      document = await pdfjs.getDocument({ data: file.bytes.slice(0) }).promise;
      for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
        try {
          const page = await document.getPage(pageNumber);
          const viewport = page.getViewport({ scale: 1 });
          const regions = pathBounds(await page.getOperatorList(), viewport);
          for (const [regionIndex, bounds] of regions.entries()) {
            try {
              const rendered = await renderRegion(page, viewport, bounds);
              artifacts.push({
                name: `${file.name}:vector-${pageNumber}-${regionIndex + 1}.png`,
                bytes: rendered.bytes,
                mediaType: "image/png",
                provenance: { page: pageNumber, bbox: [bounds.left, bounds.top, bounds.right, bounds.bottom] },
                width: rendered.width,
                height: rendered.height,
              });
            } catch (error) {
              failures.push({ document: file.name, page: pageNumber, bbox: bounds, reason: String(error) });
            }
          }
        } catch (error) {
          failures.push({ document: file.name, page: pageNumber, bbox: null, reason: String(error) });
        }
      }
    } catch (error) {
      failures.push({ document: file.name, page: null, bbox: null, reason: String(error) });
    } finally {
      if (document) {
        await document.destroy();
      }
    }
  }
  return { artifacts, failures };
}

"use client";

import { useEffect, useState } from "react";
import { BASIC_VERTEX_SHADER, EFFECTS, type EffectKey } from "@/lib/twick-effects";

const PREVIEW_WIDTH = 160;
const PREVIEW_HEIGHT = 90;
const PREVIEW_TEXTURE_SIZE = 64;

let previewCanvas: HTMLCanvasElement | null = null;
let previewContext: WebGLRenderingContext | null = null;

const previewCache = new Map<EffectKey, string>();
const pendingPreviews = new Map<EffectKey, Promise<string>>();

const ensurePreviewContext = (): WebGLRenderingContext | null => {
  if (typeof window === "undefined") {
    return null;
  }

  if (previewContext && previewCanvas) {
    return previewContext;
  }

  const canvas = document.createElement("canvas");
  canvas.width = PREVIEW_WIDTH;
  canvas.height = PREVIEW_HEIGHT;
  canvas.style.position = "absolute";
  canvas.style.left = "-9999px";
  canvas.style.top = "-9999px";
  canvas.style.width = `${PREVIEW_WIDTH}px`;
  canvas.style.height = `${PREVIEW_HEIGHT}px`;
  canvas.style.pointerEvents = "none";
  canvas.style.opacity = "0";
  document.body.appendChild(canvas);

  const context =
    canvas.getContext("webgl", { preserveDrawingBuffer: true }) ??
    canvas.getContext("experimental-webgl", { preserveDrawingBuffer: true });

  if (!context) {
    canvas.remove();
    return null;
  }

  previewCanvas = canvas;
  previewContext = context as WebGLRenderingContext;
  return previewContext;
};

const createShader = (
  context: WebGLRenderingContext,
  type: number,
  source: string,
): WebGLShader | null => {
  const shader = context.createShader(type);
  if (!shader) {
    return null;
  }

  context.shaderSource(shader, source);
  context.compileShader(shader);

  if (!context.getShaderParameter(shader, context.COMPILE_STATUS)) {
    context.deleteShader(shader);
    return null;
  }

  return shader;
};

const renderEffectPreview = async (effectKey: EffectKey): Promise<string> => {
  const context = ensurePreviewContext();
  const effect = EFFECTS[effectKey];

  if (!context || !previewCanvas || !effect) {
    return "";
  }

  const vertexShader = createShader(
    context,
    context.VERTEX_SHADER,
    BASIC_VERTEX_SHADER,
  );
  const fragmentShader = createShader(
    context,
    context.FRAGMENT_SHADER,
    effect.fragment,
  );

  if (!vertexShader || !fragmentShader) {
    if (vertexShader) {
      context.deleteShader(vertexShader);
    }
    if (fragmentShader) {
      context.deleteShader(fragmentShader);
    }
    return "";
  }

  const program = context.createProgram();
  const positionBuffer = context.createBuffer();
  const texCoordBuffer = context.createBuffer();
  const texture = context.createTexture();

  if (!program || !positionBuffer || !texCoordBuffer || !texture) {
    if (program) {
      context.deleteProgram(program);
    }
    context.deleteBuffer(positionBuffer);
    context.deleteBuffer(texCoordBuffer);
    context.deleteTexture(texture);
    context.deleteShader(vertexShader);
    context.deleteShader(fragmentShader);
    return "";
  }

  context.attachShader(program, vertexShader);
  context.attachShader(program, fragmentShader);
  context.linkProgram(program);

  if (!context.getProgramParameter(program, context.LINK_STATUS)) {
    context.deleteTexture(texture);
    context.deleteBuffer(positionBuffer);
    context.deleteBuffer(texCoordBuffer);
    context.deleteProgram(program);
    context.deleteShader(vertexShader);
    context.deleteShader(fragmentShader);
    return "";
  }

  context.useProgram(program);

  const positionLocation = context.getAttribLocation(program, "a_position");
  const texCoordLocation = context.getAttribLocation(program, "a_texCoord");

  context.bindBuffer(context.ARRAY_BUFFER, positionBuffer);
  context.bufferData(
    context.ARRAY_BUFFER,
    new Float32Array([
      -1, -1,
      1, -1,
      -1, 1,
      -1, 1,
      1, -1,
      1, 1,
    ]),
    context.STATIC_DRAW,
  );
  context.enableVertexAttribArray(positionLocation);
  context.vertexAttribPointer(positionLocation, 2, context.FLOAT, false, 0, 0);

  context.bindBuffer(context.ARRAY_BUFFER, texCoordBuffer);
  context.bufferData(
    context.ARRAY_BUFFER,
    new Float32Array([
      0, 0,
      1, 0,
      0, 1,
      0, 1,
      1, 0,
      1, 1,
    ]),
    context.STATIC_DRAW,
  );
  context.enableVertexAttribArray(texCoordLocation);
  context.vertexAttribPointer(texCoordLocation, 2, context.FLOAT, false, 0, 0);

  context.bindTexture(context.TEXTURE_2D, texture);

  const textureData = new Uint8Array(PREVIEW_TEXTURE_SIZE * PREVIEW_TEXTURE_SIZE * 4);
  for (let y = 0; y < PREVIEW_TEXTURE_SIZE; y += 1) {
    for (let x = 0; x < PREVIEW_TEXTURE_SIZE; x += 1) {
      const index = (y * PREVIEW_TEXTURE_SIZE + x) * 4;
      const fx = x / (PREVIEW_TEXTURE_SIZE - 1);
      const fy = y / (PREVIEW_TEXTURE_SIZE - 1);
      textureData[index] = Math.round(fx * 255);
      textureData[index + 1] = Math.round(fy * 255);
      textureData[index + 2] = 200;
      textureData[index + 3] = 255;
    }
  }

  context.texImage2D(
    context.TEXTURE_2D,
    0,
    context.RGBA,
    PREVIEW_TEXTURE_SIZE,
    PREVIEW_TEXTURE_SIZE,
    0,
    context.RGBA,
    context.UNSIGNED_BYTE,
    textureData,
  );
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MIN_FILTER, context.LINEAR);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_MAG_FILTER, context.LINEAR);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_S, context.CLAMP_TO_EDGE);
  context.texParameteri(context.TEXTURE_2D, context.TEXTURE_WRAP_T, context.CLAMP_TO_EDGE);

  const textureLocation = context.getUniformLocation(program, "uTexture");
  const timeLocation = context.getUniformLocation(program, "uTime");
  const intensityLocation = context.getUniformLocation(program, "uIntensity");
  const resolutionLocation = context.getUniformLocation(program, "uResolution");

  if (textureLocation !== null) {
    context.uniform1i(textureLocation, 0);
  }
  if (timeLocation !== null) {
    context.uniform1f(timeLocation, 1);
  }
  if (intensityLocation !== null) {
    context.uniform1f(intensityLocation, 0.9);
  }
  if (resolutionLocation !== null) {
    context.uniform2f(
      resolutionLocation,
      previewCanvas.width,
      previewCanvas.height,
    );
  }

  context.viewport(0, 0, previewCanvas.width, previewCanvas.height);
  context.clearColor(0, 0, 0, 1);
  context.clear(context.COLOR_BUFFER_BIT);
  context.drawArrays(context.TRIANGLES, 0, 6);

  const dataUrl = previewCanvas.toDataURL("image/png");

  context.deleteTexture(texture);
  context.deleteBuffer(positionBuffer);
  context.deleteBuffer(texCoordBuffer);
  context.deleteProgram(program);
  context.deleteShader(vertexShader);
  context.deleteShader(fragmentShader);

  return dataUrl;
};

export const getEffectPreviewForEffect = (
  effectKey: EffectKey,
): Promise<string> => {
  if (previewCache.has(effectKey)) {
    return Promise.resolve(previewCache.get(effectKey) ?? "");
  }

  if (pendingPreviews.has(effectKey)) {
    return pendingPreviews.get(effectKey) ?? Promise.resolve("");
  }

  const nextPreview = renderEffectPreview(effectKey)
    .then((dataUrl) => {
      previewCache.set(effectKey, dataUrl);
      pendingPreviews.delete(effectKey);
      return dataUrl;
    })
    .catch(() => {
      pendingPreviews.delete(effectKey);
      return "";
    });

  pendingPreviews.set(effectKey, nextPreview);
  return nextPreview;
};

interface EffectStylePreviewProps {
  effectKey: EffectKey;
}

export function EffectStylePreview({ effectKey }: EffectStylePreviewProps) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void getEffectPreviewForEffect(effectKey).then((dataUrl) => {
      if (!cancelled && dataUrl) {
        setSrc(dataUrl);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [effectKey]);

  if (!src) {
    return (
      <div className="h-full w-full bg-[radial-gradient(circle_at_top_left,_rgba(251,146,60,0.95),_rgba(220,38,38,0.85)_26%,_rgba(15,23,42,0.95)_70%)]" />
    );
  }

  return (
    <img
      src={src}
      alt=""
      className="h-full w-full object-cover"
      loading="lazy"
    />
  );
}

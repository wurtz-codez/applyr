"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const INK = 0x141410;
const PAPER = 0xf2ede2;
const LIME = 0xc9f53f;

type Orbiter = {
  pivot: THREE.Group;
  phase: number;
  speed: number;
};

/**
 * A quiet little gyroscope: ink rings, drifting dust and a lime core.
 * Flat-shaded on purpose so it reads like a printed technical diagram
 * rather than a glossy 3D toy.
 */
export function HeroObject() {
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let disposed = false;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.setAttribute("aria-hidden", "true");
    renderer.domElement.style.position = "absolute";
    renderer.domElement.style.inset = "0";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    wrap.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    camera.position.set(0, 0, 8.4);

    const root = new THREE.Group();
    const gyro = new THREE.Group();
    root.add(gyro);
    scene.add(root);

    const geometries: THREE.BufferGeometry[] = [];
    const materials: THREE.Material[] = [];
    const textures: THREE.Texture[] = [];
    const orbiters: Orbiter[] = [];

    const trackGeometry = <T extends THREE.BufferGeometry>(item: T): T => {
      geometries.push(item);
      return item;
    };
    const trackMaterial = <T extends THREE.Material>(item: T): T => {
      materials.push(item);
      return item;
    };

    const render = () => {
      renderer.render(scene, camera);
    };

    // --- orbit rings -------------------------------------------------------
    const makeRing = (
      radius: number,
      opacity: number,
      color = INK,
      arc = Math.PI * 2,
    ) => {
      const geometry = trackGeometry(
        new THREE.TorusGeometry(radius, 0.007, 3, 260, arc),
      );
      const material = trackMaterial(
        new THREE.MeshBasicMaterial({
          color,
          transparent: true,
          opacity,
          depthWrite: false,
        }),
      );
      return new THREE.Mesh(geometry, material);
    };

    const ringA = makeRing(2.62, 0.42);
    ringA.rotation.set(Math.PI / 2.35, 0.12, 0.34);
    gyro.add(ringA);

    const ringB = makeRing(2.25, 0.5);
    ringB.rotation.set(Math.PI / 1.72, -0.55, 0.85);
    gyro.add(ringB);

    const ringC = makeRing(1.94, 0.24);
    ringC.rotation.set(0.38, 0.72, -0.18);
    gyro.add(ringC);

    const limeArc = makeRing(2.1, 0.95, LIME, Math.PI * 0.62);
    limeArc.rotation.set(Math.PI / 2.2, 0.28, -0.55);
    gyro.add(limeArc);

    // --- wireframe shell ---------------------------------------------------
    const shell = new THREE.Mesh(
      trackGeometry(new THREE.IcosahedronGeometry(1.52, 2)),
      trackMaterial(
        new THREE.MeshBasicMaterial({
          color: INK,
          wireframe: true,
          transparent: true,
          opacity: 0.11,
          depthWrite: false,
        }),
      ),
    );
    gyro.add(shell);

    // --- particle dust -----------------------------------------------------
    const makeDust = (
      count: number,
      inner: number,
      outer: number,
      size: number,
      color: number,
      opacity: number,
    ) => {
      const positions = new Float32Array(count * 3);
      for (let i = 0; i < count; i += 1) {
        const y = Math.random() * 2 - 1;
        const theta = Math.random() * Math.PI * 2;
        const radius = inner + Math.cbrt(Math.random()) * (outer - inner);
        const circle = Math.sqrt(1 - y * y);
        positions[i * 3] = Math.cos(theta) * circle * radius;
        positions[i * 3 + 1] = y * radius;
        positions[i * 3 + 2] = Math.sin(theta) * circle * radius;
      }
      const geometry = trackGeometry(new THREE.BufferGeometry());
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      const material = trackMaterial(
        new THREE.PointsMaterial({
          color,
          size,
          sizeAttenuation: true,
          transparent: true,
          opacity,
          depthWrite: false,
        }),
      );
      return new THREE.Points(geometry, material);
    };

    const inkDust = makeDust(1500, 1.25, 2.85, 0.022, INK, 0.52);
    const limeDust = makeDust(120, 1.9, 2.95, 0.038, LIME, 0.95);
    gyro.add(inkDust, limeDust);

    // --- core --------------------------------------------------------------
    const core = new THREE.Mesh(
      trackGeometry(new THREE.IcosahedronGeometry(0.3, 3)),
      trackMaterial(new THREE.MeshBasicMaterial({ color: LIME })),
    );
    gyro.add(core);

    const coreRing = makeRing(0.52, 0.8, INK);
    coreRing.rotation.x = Math.PI / 2;
    coreRing.rotation.z = 0.3;
    gyro.add(coreRing);

    // soft lime halo behind the core
    const glowCanvas = document.createElement("canvas");
    glowCanvas.width = 160;
    glowCanvas.height = 160;
    const glowContext = glowCanvas.getContext("2d");
    if (glowContext) {
      const gradient = glowContext.createRadialGradient(80, 80, 0, 80, 80, 80);
      gradient.addColorStop(0, "rgba(201, 245, 63, 0.75)");
      gradient.addColorStop(0.35, "rgba(201, 245, 63, 0.28)");
      gradient.addColorStop(1, "rgba(201, 245, 63, 0)");
      glowContext.fillStyle = gradient;
      glowContext.fillRect(0, 0, 160, 160);
      const glowTexture = new THREE.CanvasTexture(glowCanvas);
      textures.push(glowTexture);
      const glow = new THREE.Sprite(
        trackMaterial(
          new THREE.SpriteMaterial({
            map: glowTexture,
            transparent: true,
            depthWrite: false,
            opacity: 0.85,
          }),
        ),
      );
      glow.scale.setScalar(2.4);
      glow.position.z = -0.35;
      gyro.add(glow);
    }

    // --- satellites --------------------------------------------------------
    const makeSatellite = (
      radius: number,
      size: number,
      color: number,
      tiltX: number,
      tiltZ: number,
      phase: number,
      speed: number,
    ) => {
      const pivot = new THREE.Group();
      pivot.rotation.set(tiltX, phase, tiltZ);
      const node = new THREE.Mesh(
        trackGeometry(new THREE.SphereGeometry(size, 18, 18)),
        trackMaterial(new THREE.MeshBasicMaterial({ color })),
      );
      node.position.x = radius;
      pivot.add(node);
      gyro.add(pivot);
      orbiters.push({ pivot, phase, speed });
    };

    makeSatellite(2.24, 0.072, INK, 0.42, 0.1, 0.4, 0.18);
    makeSatellite(1.96, 0.05, LIME, -0.5, 0.4, 2.1, -0.24);
    makeSatellite(2.62, 0.058, PAPER, 0.15, -0.35, 4.3, 0.13);
    makeSatellite(2.05, 0.042, INK, 1.1, 0.2, 5.4, 0.28);
    makeSatellite(2.86, 0.036, LIME, 0.7, 0.5, 3.2, -0.1);
    makeSatellite(2.32, 0.03, INK, -1.2, -0.2, 1.3, 0.2);

    // --- responsive sizing -------------------------------------------------
    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      const smallest = Math.min(width, height);
      const scale = smallest < 460 ? 0.68 : smallest < 620 ? 0.9 : 1.08;
      root.scale.setScalar(scale);
      if (reduceMotion) render();
    };

    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    resize();

    // --- pointer + scroll --------------------------------------------------
    const pointer = { x: 0, y: 0 };
    const target = { x: 0, y: 0 };
    let scrollY = window.scrollY;

    const onPointerMove = (event: PointerEvent) => {
      if (reduceMotion || event.pointerType === "touch") return;
      const rect = wrap.getBoundingClientRect();
      target.x = THREE.MathUtils.clamp(
        ((event.clientX - rect.left) / rect.width - 0.5) * 2,
        -1.2,
        1.2,
      );
      target.y = THREE.MathUtils.clamp(
        ((event.clientY - rect.top) / rect.height - 0.5) * 2,
        -1.2,
        1.2,
      );
    };
    const onScroll = () => {
      scrollY = window.scrollY;
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });

    // --- render loop -------------------------------------------------------
    const timer = new THREE.Timer();
    let frame = 0;
    let inView = true;
    let running = false;

    const tick = (timestamp?: number) => {
      timer.update(timestamp);
      const time = timer.getElapsed();
      const drift = reduceMotion ? 0 : 1;

      gyro.rotation.y = time * 0.075 * drift;
      gyro.rotation.x = Math.sin(time * 0.11) * 0.07 * drift;
      inkDust.rotation.y = -time * 0.035 * drift;
      limeDust.rotation.y = time * 0.05 * drift;
      limeArc.rotation.z = -0.55 + time * 0.16 * drift;
      shell.rotation.y = -time * 0.02 * drift;
      shell.rotation.x = time * 0.015 * drift;

      orbiters.forEach((orbiter) => {
        orbiter.pivot.rotation.y = orbiter.phase + time * orbiter.speed * drift;
      });

      const breath = 1 + Math.sin(time * 0.55) * 0.012 * drift;
      core.scale.setScalar(breath);

      pointer.x += (target.x - pointer.x) * 0.045;
      pointer.y += (target.y - pointer.y) * 0.045;

      const scrollTurn = scrollY * 0.0004;
      root.rotation.y += (pointer.x * 0.24 + scrollTurn - root.rotation.y) * 0.06;
      root.rotation.x +=
        (-pointer.y * 0.16 + scrollTurn * 0.35 - root.rotation.x) * 0.06;

      render();

      if (running) frame = window.requestAnimationFrame(tick);
    };

    const start = () => {
      if (running) return;
      running = true;
      frame = window.requestAnimationFrame(tick);
    };

    const stop = () => {
      running = false;
      window.cancelAnimationFrame(frame);
    };

    const onVisibility = () => {
      if (document.hidden) stop();
      else if (inView && !reduceMotion) start();
    };

    const intersection = new IntersectionObserver(
      ([entry]) => {
        inView = entry.isIntersecting;
        if (inView && !reduceMotion && !document.hidden) start();
        else stop();
      },
      { threshold: 0.01 },
    );
    intersection.observe(wrap);

    document.addEventListener("visibilitychange", onVisibility);

    if (reduceMotion) {
      render();
      window.requestAnimationFrame(() => {
        if (disposed) return;
        resize();
        render();
      });
    } else {
      start();
    }

    return () => {
      disposed = true;
      stop();
      observer.disconnect();
      intersection.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("scroll", onScroll);
      timer.dispose();
      textures.forEach((texture) => texture.dispose());
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => material.dispose());
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={wrapRef} className="lp-canvas" aria-hidden="true" />;
}

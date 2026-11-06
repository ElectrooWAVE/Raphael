"use client";

import React, { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from "react";
import * as THREE from "three";
import { AlertTriangle, Camera, Maximize2, Minimize2, RefreshCcw, Sparkles } from "lucide-react";

export interface TelemetryInfo {
  geometries: number;
  textures: number;
  programs: number;
  fps: number;
  active: boolean;
  triangles?: number;
}

export interface SplineSceneHandle {
  captureRotationSnapshot: (rotationY: number) => Promise<string>;
  resetCamera: () => void;
}

export interface SplineSceneWrapperProps {
  sceneUrl?: string;
  className?: string;
  onTelemetry?: (info: TelemetryInfo) => void;
  aspectRatio?: string;
  fallbackTitle?: string;
  showBadge?: boolean;
  borderless?: boolean;
  showControls?: boolean;
}

const SplineSceneWrapper = forwardRef<SplineSceneHandle, SplineSceneWrapperProps>(
  function SplineSceneWrapper(
    {
      sceneUrl = process.env.NEXT_PUBLIC_SPLINE_URL,
      className = "",
      onTelemetry,
      aspectRatio = "aspect-[4/3] sm:aspect-[16/10]",
      fallbackTitle = "Liquid Iridescent Chromatic Ribbon",
      showBadge = false,
      borderless = false,
      showControls = false,
    },
    ref
  ) {
    const containerRef = useRef<HTMLDivElement>(null);

    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [useProcedural, setUseProcedural] = useState<boolean>(!sceneUrl);
    const [splineFailed, setSplineFailed] = useState<boolean>(false);
    const [webglAvailable, setWebglAvailable] = useState<boolean>(true);
    const [isExpanded, setIsExpanded] = useState<boolean>(false);
    const [isReducedMotion, setIsReducedMotion] = useState<boolean>(false);
    const [isMobile, setIsMobile] = useState<boolean>(false);

    // References for Three.js state & camera reset
    const threeState = useRef<{
      canvas: HTMLCanvasElement | null;
      renderer: THREE.WebGLRenderer | null;
      scene: THREE.Scene | null;
      camera: THREE.PerspectiveCamera | null;
      mesh: THREE.Mesh | null;
      geometry: THREE.BufferGeometry | null;
      material: THREE.MeshPhysicalMaterial | null;
      lights: THREE.Light[];
      envTexture: THREE.CanvasTexture | null;
      pmremGenerator: THREE.PMREMGenerator | null;
      envRenderTarget: THREE.WebGLRenderTarget | null;
      uniforms: { uTime: { value: number } };
      animId: number | null;
      targetRotation: { x: number; y: number };
      defaultRotation: { x: number; y: number };
      isPaused: boolean;
    }>({
      canvas: null,
      renderer: null,
      scene: null,
      camera: null,
      mesh: null,
      geometry: null,
      material: null,
      lights: [],
      envTexture: null,
      pmremGenerator: null,
      envRenderTarget: null,
      uniforms: { uTime: { value: 0 } },
      animId: null,
      targetRotation: { x: 0.35, y: 0.45 },
      defaultRotation: { x: 0.35, y: 0.45 },
      isPaused: false,
    });

    // Check client environment: reduced motion & mobile viewport (<768px)
    useEffect(() => {
      const checkMedia = () => {
        const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
        setIsReducedMotion(motionQuery.matches);
        setIsMobile(window.innerWidth < 768);
      };

      checkMedia();
      window.addEventListener("resize", checkMedia);
      return () => window.removeEventListener("resize", checkMedia);
    }, []);

    // Reset Camera Utility
    const handleResetCamera = useCallback(() => {
      const s = threeState.current;
      if (s.mesh) {
        s.targetRotation.x = s.defaultRotation.x;
        s.targetRotation.y = s.defaultRotation.y;
      }
    }, []);

    // Expose capture snapshot and reset methods via ref
    useImperativeHandle(
      ref,
      () => ({
        resetCamera: handleResetCamera,
        captureRotationSnapshot: async (rotationY: number) => {
          const s = threeState.current;
          if (!s.renderer || !s.scene || !s.camera || !s.mesh) return "";

          // Set specific rotation for snapshot
          s.mesh.rotation.y = rotationY;
          s.renderer.render(s.scene, s.camera);
          return s.renderer.domElement.toDataURL("image/png");
        },
      }),
      [handleResetCamera]
    );

    // Toggle Expand Utility
    const handleToggleExpand = useCallback(() => {
      setIsExpanded((prev) => !prev);
    }, []);

    // Initialize Three.js Procedural Scene (Visual Round 2 Approach)
    useEffect(() => {
      if (!useProcedural && !splineFailed) return;
      if (isReducedMotion || isMobile) {
        setIsLoading(false);
        return;
      }

      const container = containerRef.current;
      if (!container) return;

      // 1. Feature-detect WebGL before creating renderer
      const testCanvas = document.createElement("canvas");
      const testGl =
        testCanvas.getContext("webgl2") ||
        testCanvas.getContext("webgl") ||
        testCanvas.getContext("experimental-webgl");
      if (!testGl) {
        setWebglAvailable(false);
        setIsLoading(false);
        return;
      }
      setWebglAvailable(true);

      // 2. Create fresh canvas element inside effect (never reuse after forceContextLoss)
      const canvas = document.createElement("canvas");
      canvas.className = "absolute inset-0 h-full w-full block cursor-grab active:cursor-grabbing";
      container.appendChild(canvas);

      const handleContextLost = (e: Event) => {
        e.preventDefault();
        setWebglAvailable(false);
        if (threeState.current.animId) {
          cancelAnimationFrame(threeState.current.animId);
          threeState.current.animId = null;
        }
      };
      canvas.addEventListener("webglcontextlost", handleContextLost, false);

      let width = container.clientWidth || 600;
      let height = container.clientHeight || 450;

      // 3. Scene, Camera, Renderer
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
      camera.position.set(0, 0, 8.5);

      const renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: true, // Allows clean toDataURL snapshots
      });

      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setClearColor(0x000000, 0); // Transparent canvas over pure black
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.28; // Brighten slightly per user feedback

      // 4. OFFLINE Smooth 360° Gradient Environment Map via PMREMGenerator
      // Rich luminous violet, electric blue, radiant cyan, and magenta gradients
      const envCanvas = document.createElement("canvas");
      envCanvas.width = 1024;
      envCanvas.height = 512;
      const ctx = envCanvas.getContext("2d");
      if (ctx) {
        // Deep obsidian navy base (no brown/maroon)
        ctx.fillStyle = "#040510";
        ctx.fillRect(0, 0, 1024, 512);

        // Radiant Cyan #00F2FE sweep (upper-left)
        const gCyan = ctx.createRadialGradient(280, 160, 20, 280, 160, 340);
        gCyan.addColorStop(0, "#00F2FE");
        gCyan.addColorStop(0.45, "rgba(0, 242, 254, 0.85)");
        gCyan.addColorStop(1, "rgba(0, 242, 254, 0)");
        ctx.fillStyle = gCyan;
        ctx.fillRect(0, 0, 1024, 512);

        // Radiant Luminous Violet #8B5CF6 & Royal Blue #3B82F6 sweep (upper-center)
        const gVio = ctx.createRadialGradient(512, 110, 30, 512, 110, 320);
        gVio.addColorStop(0, "#8B5CF6");
        gVio.addColorStop(0.5, "rgba(59, 130, 246, 0.8)");
        gVio.addColorStop(1, "rgba(139, 92, 246, 0)");
        ctx.fillStyle = gVio;
        ctx.fillRect(0, 0, 1024, 512);

        // Radiant Magenta #EC4899 sweep (right)
        const gMag = ctx.createRadialGradient(780, 280, 20, 780, 280, 330);
        gMag.addColorStop(0, "#EC4899");
        gMag.addColorStop(0.5, "rgba(236, 72, 153, 0.7)");
        gMag.addColorStop(1, "rgba(236, 72, 153, 0)");
        ctx.fillStyle = gMag;
        ctx.fillRect(0, 0, 1024, 512);

        // Radiant Amber #F59E0B subtle accent (lower-right)
        const gAmb = ctx.createRadialGradient(890, 170, 20, 890, 170, 240);
        gAmb.addColorStop(0, "#F59E0B");
        gAmb.addColorStop(0.5, "rgba(245, 158, 11, 0.5)");
        gAmb.addColorStop(1, "rgba(245, 158, 11, 0)");
        ctx.fillStyle = gAmb;
        ctx.fillRect(0, 0, 1024, 512);

        // Crisp white specular accent glint
        const gWhite = ctx.createRadialGradient(380, 220, 10, 380, 220, 140);
        gWhite.addColorStop(0, "#FFFFFF");
        gWhite.addColorStop(0.4, "rgba(255, 255, 255, 0.9)");
        gWhite.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = gWhite;
        ctx.fillRect(0, 0, 1024, 512);
      }

      const envTexture = new THREE.CanvasTexture(envCanvas);
      envTexture.mapping = THREE.EquirectangularReflectionMapping;
      envTexture.colorSpace = THREE.SRGBColorSpace;

      const pmremGenerator = new THREE.PMREMGenerator(renderer);
      pmremGenerator.compileEquirectangularShader();
      const envRenderTarget = pmremGenerator.fromEquirectangular(envTexture);
      scene.environment = envRenderTarget.texture;

      // 5. Slender Twisted Fluid Ribbon Knot Geometry
      // Radius 2.0, tube 0.19 with vertical compactness to guarantee zero top canvas clipping
      const geometry = new THREE.TorusKnotGeometry(2.0, 0.19, 384, 48, 2, 3);

      // 6. Shader Uniforms for Dynamic Chromatic Shimmer
      const uniforms = {
        uTime: { value: 0 },
      };

      // 7. Tuned MeshPhysicalMaterial with Metalness + Iridescence (Deep Royal Sapphire Violet-Blue Core)
      const material = new THREE.MeshPhysicalMaterial({
        color: 0x3730a3, // Noticeably vivid royal violet/blue body (indigo-violet)
        emissive: 0x1e1b4b, // Rich luminous deep violet undertone
        metalness: 0.55,
        roughness: 0.06,
        iridescence: 1.0,
        iridescenceIOR: 1.95, // High IOR for brilliant chromatic iridescent rim
        iridescenceThicknessRange: [280, 1100],
        clearcoat: 1.0,
        clearcoatRoughness: 0.02,
        envMapIntensity: 4.2, // Brighter iridescent rim reflection
        reflectivity: 0.99,
      });

      // 8. Custom Fresnel Color Shift via onBeforeCompile
      // Shifts hue with view angle and surface normal: vivid cyan, violet, magenta, and amber glints
      material.customProgramCacheKey = () => "chromatic_ribbon_v7";
      material.onBeforeCompile = (shader) => {
        shader.uniforms.uTime = uniforms.uTime;

        shader.fragmentShader = `
          uniform float uTime;
        ` + shader.fragmentShader;

        shader.fragmentShader = shader.fragmentShader.replace(
          "#include <opaque_fragment>",
          `
          #include <opaque_fragment>

          // Dynamic chromatic fresnel shift (Cosine color palette on surface rim)
          vec3 viewDirVec = normalize( -vViewPosition );
          vec3 normDirVec = normalize( vNormal );
          float fresnelAngle = 1.0 - clamp( abs( dot( viewDirVec, normDirVec ) ), 0.0, 1.0 );
          float fresnelRim = pow( fresnelAngle, 2.2 );

          // Cosine palette parameters: cyan -> violet -> magenta -> small amber
          float colorT = fresnelAngle * 1.8 + (normDirVec.x * 0.4 + normDirVec.y * 0.25) + uTime * 0.08;
          vec3 palA = vec3(0.5, 0.5, 0.5);
          vec3 palB = vec3(0.5, 0.5, 0.5);
          vec3 palC = vec3(1.0, 1.0, 1.0);
          vec3 palD = vec3(0.00, 0.33, 0.67);
          vec3 spectralColor = palA + palB * cos( 6.2831853 * ( palC * colorT + palD ) );

          // Strong brand cyan #00F2FE and electric violet #8B5CF6 weighting
          spectralColor = mix(spectralColor, vec3(0.0, 0.96, 1.0), 0.45); // Electric Cyan
          spectralColor = mix(spectralColor, vec3(0.68, 0.28, 1.0), 0.55); // Radiant Electric Violet

          // Amber warm highlights on upper-right crests
          float amberDot = clamp(normDirVec.x * 0.6 + normDirVec.y * 0.5, 0.0, 1.0);
          spectralColor += vec3(0.96, 0.62, 0.04) * pow(amberDot, 4.0) * 0.65;

          // Additive rim emission in linear HDR space before tone mapping
          gl_FragColor.rgb += spectralColor * fresnelRim * 4.8;
          `
        );
      };

      const mesh = new THREE.Mesh(geometry, material);
      mesh.scale.set(1.04, 0.95, 0.85); // Organic sweeping ribbon silhouette with controlled vertical height
      mesh.rotation.set(0.35, 0.45, 0.1);
      mesh.position.set(0.18, -0.25, 0); // Positioned lower with generous vertical headroom; bleeds only off right viewport edge
      camera.position.set(0, 0, 9.8);
      scene.add(mesh);

      // 9. Directed Key & Studio Lights with Cool Blue Fill & Cyan Rim
      const lights: THREE.Light[] = [];

      const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
      keyLight.position.set(4, 6, 6);
      scene.add(keyLight);
      lights.push(keyLight);

      const coolFillLight = new THREE.DirectionalLight(0x818cf8, 1.4);
      coolFillLight.position.set(-5, -2, 4);
      scene.add(coolFillLight);
      lights.push(coolFillLight);

      const cyanRimLight = new THREE.DirectionalLight(0x00f2fe, 1.8);
      cyanRimLight.position.set(5, -3, -4);
      scene.add(cyanRimLight);
      lights.push(cyanRimLight);

      const ambientLight = new THREE.AmbientLight(0x1e1b4b, 0.55);
      scene.add(ambientLight);
      lights.push(ambientLight);

      // Store references in state
      const s = threeState.current;
      s.canvas = canvas;
      s.renderer = renderer;
      s.scene = scene;
      s.camera = camera;
      s.mesh = mesh;
      s.geometry = geometry;
      s.material = material;
      s.lights = lights;
      s.envTexture = envTexture;
      s.pmremGenerator = pmremGenerator;
      s.envRenderTarget = envRenderTarget;
      s.uniforms = uniforms;
      s.targetRotation = { x: 0.35, y: 0.45 };
      s.defaultRotation = { x: 0.35, y: 0.45 };
      s.isPaused = false;

      // 10. Mouse Move Interaction & Custom Rotation Events
      const handlePointerMove = (e: MouseEvent) => {
        const rect = container.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        const ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
        s.targetRotation.y = s.defaultRotation.y + nx * 0.45;
        s.targetRotation.x = s.defaultRotation.x - ny * 0.35;
      };
      window.addEventListener("mousemove", handlePointerMove, { passive: true });

      const handleCustomRotation = (e: Event) => {
        const customEvent = e as CustomEvent<{ rotationY: number }>;
        if (customEvent.detail && typeof customEvent.detail.rotationY === "number" && s.mesh) {
          s.mesh.rotation.y = customEvent.detail.rotationY;
          s.targetRotation.y = customEvent.detail.rotationY;
          s.targetRotation.x = s.defaultRotation.x;
          if (s.renderer && s.scene && s.camera) {
            s.renderer.render(s.scene, s.camera);
          }
        }
      };
      window.addEventListener("raphael:set-rotation", handleCustomRotation);

      // 11. Responsive Resize
      const handleResize = () => {
        if (!container || !s.renderer || !s.camera) return;
        width = container.clientWidth || 600;
        height = container.clientHeight || 450;
        s.camera.aspect = width / height;
        s.camera.updateProjectionMatrix();
        s.renderer.setSize(width, height);
      };
      window.addEventListener("resize", handleResize);

      // 12. IntersectionObserver (Pause Render Loop Off-screen)
      const observer = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          s.isPaused = !entry.isIntersecting;
        },
        { threshold: 0.05 }
      );
      observer.observe(container);

      // 13. Animation Loop with Telemetry & FPS Calculation
      let lastTime = performance.now();
      let frameCount = 0;
      let fps = 60;

      const animate = (now: number) => {
        s.animId = requestAnimationFrame(animate);

        // Skip render if off-screen
        if (s.isPaused) return;

        // Update shader time uniform for subtle dynamic shimmer
        uniforms.uTime.value = now * 0.001;

        // Smooth slow continuous ribbon rotation + gentle mouse response
        if (mesh) {
          mesh.rotation.y += (s.targetRotation.y - mesh.rotation.y) * 0.04 + 0.0035;
          mesh.rotation.x += (s.targetRotation.x - mesh.rotation.x) * 0.04;
          mesh.rotation.z += 0.002;
        }

        renderer.render(scene, camera);

        // FPS tracking & live telemetry
        frameCount++;
        const elapsed = now - lastTime;
        if (elapsed >= 500) {
          fps = Math.round((frameCount * 1000) / elapsed);
          frameCount = 0;
          lastTime = now;

          if (onTelemetry && s.renderer) {
            onTelemetry({
              geometries: s.renderer.info.memory.geometries,
              textures: s.renderer.info.memory.textures,
              programs: s.renderer.info.programs?.length || 0,
              triangles: s.renderer.info.render.triangles,
              fps,
              active: true,
            });
          }
        }
      };

      s.animId = requestAnimationFrame(animate);
      setIsLoading(false);

      // 14. Full Teardown on Unmount
      return () => {
        if (s.animId !== null) {
          cancelAnimationFrame(s.animId);
          s.animId = null;
        }
        canvas.removeEventListener("webglcontextlost", handleContextLost);
        window.removeEventListener("mousemove", handlePointerMove);
        window.removeEventListener("raphael:set-rotation", handleCustomRotation);
        window.removeEventListener("resize", handleResize);
        observer.disconnect();

        // Dispose environment map & PMREM resources
        if (envRenderTarget) {
          envRenderTarget.dispose();
        }
        if (pmremGenerator) {
          pmremGenerator.dispose();
        }
        if (envTexture) {
          envTexture.dispose();
        }

        // Dispose lights
        lights.forEach((light) => scene.remove(light));

        // Dispose mesh, geometry, material
        if (mesh) scene.remove(mesh);
        if (geometry) geometry.dispose();
        if (material) material.dispose();

        // Dispose WebGLRenderer and force context loss
        if (renderer) {
          renderer.dispose();
          renderer.forceContextLoss();
        }

        // Remove canvas from DOM
        if (canvas.parentNode === container) {
          container.removeChild(canvas);
        }

        // Report zeroed telemetry to parent
        if (onTelemetry) {
          onTelemetry({
            geometries: 0,
            textures: 0,
            programs: 0,
            triangles: 0,
            fps: 0,
            active: false,
          });
        }

        s.canvas = null;
        s.renderer = null;
        s.scene = null;
        s.camera = null;
        s.mesh = null;
        s.geometry = null;
        s.material = null;
        s.envTexture = null;
        s.pmremGenerator = null;
        s.envRenderTarget = null;
        s.lights = [];
      };
    }, [useProcedural, splineFailed, isReducedMotion, isMobile, onTelemetry]);

    return (
      <div
        ref={containerRef}
        className={`relative w-full transition-all duration-300 ${
          isExpanded
            ? "fixed inset-4 z-50 rounded-3xl border border-white/[0.2] bg-black/95 backdrop-blur-3xl shadow-[0_0_80px_rgba(0,0,0,0.9)] max-w-none max-h-none h-[calc(100vh-2rem)] overflow-hidden"
            : borderless
            ? `${aspectRatio} bg-transparent overflow-visible ${className}`
            : `${aspectRatio} rounded-2xl border border-white/[0.08] bg-white/[0.02] shadow-[0_8px_32px_0_rgba(0,0,0,0.37)] overflow-hidden ${className}`
        }`}
      >
        {/* Skeleton / Loading Placeholder (Radial Pulse, Zero Layout Shift) */}
        {isLoading && (
          <div className={`absolute inset-0 flex flex-col items-center justify-center ${borderless ? "bg-transparent" : "bg-black/80"} z-20 space-y-3`}>
            <div className="relative flex items-center justify-center">
              <div className="h-16 w-16 rounded-full bg-[#00F2FE]/20 animate-ping" />
              <div className="absolute h-10 w-10 rounded-full bg-[#00F2FE]/40 animate-pulse border border-[#00F2FE]/60" />
              <Sparkles className="absolute h-5 w-5 text-[#00F2FE]" />
            </div>
          </div>
        )}

        {/* Reduced Motion, Mobile (<768px), or WebGL-Unavailable Fallback */}
        {(isReducedMotion || isMobile || !webglAvailable) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center z-10 bg-radial from-[#00F2FE]/15 via-[#A855F7]/10 to-transparent">
            <div className="relative h-48 w-48 mb-4 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-[#00F2FE]/20 via-[#A855F7]/30 to-[#EC4899]/20 blur-2xl animate-pulse" />
              {/* Elegant SVG Torus Ribbon knot wireframe */}
              <svg
                viewBox="0 0 200 200"
                className="relative h-40 w-40 text-[#00F2FE] drop-shadow-[0_0_15px_rgba(0,242,254,0.5)]"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <ellipse cx="100" cy="100" rx="80" ry="35" transform="rotate(-30 100 100)" />
                <ellipse cx="100" cy="100" rx="80" ry="35" transform="rotate(30 100 100)" />
                <circle cx="100" cy="100" r="55" strokeDasharray="4 4" opacity="0.6" />
                <path
                  d="M 50 100 Q 100 30 150 100 T 50 100"
                  stroke="url(#spectralGradient)"
                  strokeWidth="3"
                />
                <defs>
                  <linearGradient id="spectralGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#00F2FE" />
                    <stop offset="50%" stopColor="#EC4899" />
                    <stop offset="100%" stopColor="#F59E0B" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div className="text-xs font-semibold text-white tracking-wide">
              {fallbackTitle}
            </div>
            <p className="text-[11px] text-zinc-400 mt-1 max-w-xs">
              {!webglAvailable
                ? "3D hardware acceleration is currently unavailable in this environment. Clean static presentation displayed."
                : isReducedMotion
                ? "Static presentation active (prefers-reduced-motion detected)."
                : "Lightweight presentation active on compact mobile display."}
            </p>
            {!webglAvailable && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/25">
                <AlertTriangle className="h-3 w-3" />
                <span>3D unavailable (WebGL context unacquirable)</span>
              </div>
            )}
          </div>
        )}

        {/* Floating Canvas Utility Buttons (Top-Right, optional) */}
        {showControls && (
          <div className="absolute top-3 right-3 z-30 flex items-center gap-2">
            <button
              onClick={handleResetCamera}
              title="Reset Camera Orientation"
              className="glass-pill p-2 text-zinc-300 hover:text-white hover:bg-white/[0.1] border border-white/[0.12] transition-colors cursor-pointer"
            >
              <RefreshCcw className="h-3.5 w-3.5" />
            </button>

            <button
              onClick={handleToggleExpand}
              title={isExpanded ? "Minimize Canvas" : "Expand Canvas View"}
              className="glass-pill p-2 text-zinc-300 hover:text-white hover:bg-white/[0.1] border border-white/[0.12] transition-colors cursor-pointer"
            >
              {isExpanded ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        )}

        {/* Mode Indicator Badge (Bottom-Left) */}
        {showBadge && (
          <div className="absolute bottom-3 left-3 z-30 pointer-events-none">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider bg-black/60 border border-white/[0.1] text-zinc-300 backdrop-blur-md">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00F2FE] shadow-[0_0_8px_#00F2FE]" />
              <span>
                {!webglAvailable
                  ? "Static Fallback"
                  : useProcedural
                  ? "Three.js Chromatic Shimmer"
                  : "Spline Interactive Scene"}
              </span>
            </div>
          </div>
        )}
      </div>
    );
  }
);

export default SplineSceneWrapper;

"use client";

import { useEffect, useLayoutEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function LandingMotion({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useIsomorphicLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;

    gsap.registerPlugin(ScrollTrigger);

    const mm = gsap.matchMedia();

    const ctx = gsap.context(() => {
      // ---------------------------------------------------------------- intro
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const intro = gsap.timeline({
          defaults: { ease: "power4.out" },
        });

        intro
          .from(".lp-nav", { yPercent: -140, duration: 0.9 })
          .from(".lp-eyebrow", { y: 16, opacity: 0, duration: 0.8 }, 0.15)
          .from(
            ".lp-hero-title .lp-line > span",
            { yPercent: 112, rotate: 2.5, duration: 1.15, stagger: 0.09 },
            0.18,
          )
          .from(".lp-hero-sub", { y: 18, opacity: 0, duration: 0.9 }, 0.62)
          .from(".lp-hero-actions", { y: 18, opacity: 0, duration: 0.9 }, 0.72)
          .from(".lp-visual-meta", { opacity: 0, duration: 0.9 }, 0.55)
          .from(
            ".lp-chip",
            {
              opacity: 0,
              scale: 0.65,
              duration: 0.9,
              stagger: 0.09,
              ease: "back.out(2.2)",
            },
            0.7,
          )
          .from(
            ".lp-canvas",
            { opacity: 0, scale: 0.9, duration: 1.6, ease: "power3.out" },
            0.1,
          )
          .from(".lp-scroll-note", { opacity: 0, duration: 1 }, 1.1);

        // Chips drift, each at its own pace. Tilt lives in CSS `rotate`
        // so these tweens only touch the vertical offset.
        gsap.utils.toArray<HTMLElement>(".lp-chip").forEach((chip, index) => {
          gsap.to(chip, {
            y: index % 2 === 0 ? -9 : 9,
            duration: 3.2 + index * 0.45,
            repeat: -1,
            yoyo: true,
            ease: "sine.inOut",
            delay: 1.4 + index * 0.2,
          });
        });

        // gentle depth as the hero leaves
        gsap.to(".lp-hero-copy", {
          yPercent: -7,
          opacity: 0.3,
          ease: "none",
          scrollTrigger: {
            trigger: ".lp-hero",
            start: "top top",
            end: "bottom top",
            scrub: 0.6,
          },
        });
        gsap.to(".lp-hero-visual", {
          yPercent: 9,
          ease: "none",
          scrollTrigger: {
            trigger: ".lp-hero",
            start: "top top",
            end: "bottom top",
            scrub: 0.6,
          },
        });

        // ------------------------------------------------------- section reveals
        gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((element) => {
          gsap.from(element, {
            y: 38,
            opacity: 0,
            duration: 1.05,
            ease: "power3.out",
            scrollTrigger: {
              trigger: element,
              start: "top 87%",
              once: true,
            },
          });
        });

        // ----------------------------------------------------------- match card
        const card = root.querySelector<HTMLElement>(".lp-match-card");
        if (card) {
          const scoreElement = card.querySelector<HTMLElement>("[data-score]");
          const counter = { value: 0 };
          const fillTrigger = {
            trigger: card,
            start: "top 78%",
            once: true,
          } as const;

          const timeline = gsap.timeline({ scrollTrigger: fillTrigger });
          timeline
            .from(card, { y: 54, opacity: 0, duration: 1.05, ease: "power3.out" })
            .from(
              card.querySelectorAll(".lp-bar-fill"),
              {
                scaleX: 0,
                transformOrigin: "left center",
                duration: 1.05,
                stagger: 0.1,
                ease: "power3.out",
              },
              0.18,
            )
            .from(
              card.querySelectorAll(".lp-chip-small"),
              {
                y: 10,
                opacity: 0,
                duration: 0.5,
                stagger: 0.06,
                ease: "power2.out",
              },
              0.35,
            )
            .to(
              counter,
              {
                value: 92,
                duration: 1.6,
                ease: "power2.out",
                onUpdate: () => {
                  if (scoreElement) {
                    scoreElement.textContent = String(Math.round(counter.value));
                  }
                },
              },
              0.1,
            );

          gsap.from(".lp-seal", {
            scale: 0.65,
            opacity: 0,
            rotate: -40,
            duration: 0.9,
            ease: "back.out(1.7)",
            scrollTrigger: fillTrigger,
          });
        }
      });

      // ------------------------------------------ horizontal steps (desktop)
      mm.add(
        "(prefers-reduced-motion: no-preference) and (min-width: 901px)",
        () => {
          const section = root.querySelector<HTMLElement>(".lp-system");
          const track = root.querySelector<HTMLElement>(".lp-track");
          if (!section || !track) return;

          root.classList.add("lp-pin-ready");

          const distance = () =>
            Math.max(0, track.scrollWidth - window.innerWidth + 64);

          gsap.to(track, {
            x: () => -distance(),
            ease: "none",
            scrollTrigger: {
              trigger: section,
              start: "top top",
              end: () => `+=${distance() + window.innerHeight * 0.3}`,
              pin: true,
              scrub: 0.8,
              anticipatePin: 1,
              invalidateOnRefresh: true,
            },
          });

          window.requestAnimationFrame(() => ScrollTrigger.refresh());

          return () => {
            root.classList.remove("lp-pin-ready");
          };
        },
      );

      // --------------------------------------------- stacked steps (mobile)
      mm.add(
        "(prefers-reduced-motion: no-preference) and (max-width: 900px)",
        () => {
          gsap.utils.toArray<HTMLElement>(".lp-step").forEach((step) => {
            gsap.from(step, {
              y: 32,
              opacity: 0,
              duration: 0.85,
              ease: "power3.out",
              scrollTrigger: {
                trigger: step,
                start: "top 90%",
                once: true,
              },
            });
          });
        },
      );
    }, root);

    const refresh = () => ScrollTrigger.refresh();
    if (document.fonts) {
      void document.fonts.ready.then(refresh).catch(() => undefined);
    }
    window.addEventListener("load", refresh);

    return () => {
      window.removeEventListener("load", refresh);
      mm.revert();
      ctx.revert();
    };
  }, []);

  return (
    <div ref={ref} className="lp-motion">
      {children}
    </div>
  );
}

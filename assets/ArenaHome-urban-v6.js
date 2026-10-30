import{b as o,S as N,d as b,L as z,e as y,U as w,B as I,j as e,h as C,n as S,k as g,c as R}from"./card-image-preview-C175IomB.js";import{o as P}from"./chessplayerFacts-DL_9PpXO.js";import{h as W}from"./site-v7.js";import"./preload-helper-DMGCcr4D.js";

function u({to:r,navigate:d,children:l,className:c="",...h}){
  return e.jsx("a",{
    href:r,
    className:c,
    onClick:a=>{
      a.defaultPrevented||a.button!==0||a.metaKey||a.ctrlKey||a.shiftKey||a.altKey||(a.preventDefault(),d(r))
    },
    ...h,
    children:l
  });
}

function O({navigate:r,onSearch:d}){
  const[c,h]=o.useState("");
  const k=s=>{s.preventDefault(),d?.(c.trim())};

  // Bottom-right minimalist icon dock (homage to Wanxiangqi lobby "棋手 / 卡牌 / 阵容 + 开始游戏")
  const dockItems=[
    {label:"棋手",to:"/players",Icon:w},
    {label:"卡牌",to:"/atlas",Icon:N},
    {label:"阵容",to:"/wxq-lineups",Icon:R},
    {label:"克制链",to:"/counters",Icon:z},
    {label:"数值研究",to:"/analysis/dps",Icon:S}
  ];

  // Clean quick links for bottom-left search console
  const quickTags=[
    {label:"英雄图鉴 (86)",to:"/explore/hero-sulie"},
    {label:"装备合成 (95)",to:"/explore/equipment-catalog"},
    {label:"天赋词条 (297)",to:"/explore/talent-catalog"},
    {label:"效果牌库 (98)",to:"/explore/effect-catalog"},
    {label:"钻石狂潮",to:"/modes/diamond-frenzy?tab=packs"},
    {label:"抽卡模拟",to:"/analysis/draw"}
  ];

  return e.jsxs("div",{
    className:"lm-home",
    children:[
      /* Fullscreen Unobstructed Official KV Artwork */
      e.jsxs("div",{
        className:"lm-backdrop",
        "aria-hidden":"true",
        children:[
          e.jsx("img",{src:"/assets/official-kv.jpg",alt:""}),
          e.jsx("div",{className:"lm-vignette"})
        ]
      }),

      /* Bottom-Anchored Clean HUD (Zero face occlusion on upper 75% of screen) */
      e.jsx("section",{
        className:"lm-hud",
        children:e.jsxs("div",{
          className:"lm-hud-bottom",
          children:[
            /* Bottom-Left: Brand Title + Search Bar + Minimal Text Links */
            e.jsxs("div",{
              className:"lm-console-left",
              children:[
                e.jsxs("div",{
                  className:"lm-brand-hero",
                  children:[
                    e.jsxs("div",{
                      className:"lm-eyebrow-row",
                      children:[
                        e.jsx("i",{className:"lm-pulse"}),
                        e.jsx("span",{children:"S1 万象启程 · 74 篇实战阵容笔记 · 1,492 实体克制图谱"})
                      ]
                    }),
                    e.jsx("h1",{className:"lm-chrome-title",children:"万象棋笔记"})
                  ]
                }),

                e.jsxs("form",{
                  className:"lm-glass-search",
                  onSubmit:k,
                  children:[
                    e.jsx(C,{size:16,"aria-hidden":"true"}),
                    e.jsx("input",{
                      value:c,
                      onChange:s=>h(s.target.value),
                      placeholder:"搜索英雄、装备、天赋、阵容笔记…",
                      "aria-label":"搜索万象棋笔记"
                    }),
                    e.jsx("button",{type:"submit",children:"检索"})
                  ]
                }),

                e.jsx("nav",{
                  className:"lm-quick-links",
                  "aria-label":"快速图鉴入口",
                  children:quickTags.map(item=>e.jsx(u,{
                    to:item.to,
                    navigate:r,
                    className:"lm-quick-link",
                    children:item.label
                  },item.to))
                })
              ]
            }),

            /* Bottom-Right: Game Lobby Style Icon Dock + Primary CTA */
            e.jsxs("div",{
              className:"lm-lobby-dock",
              children:[
                e.jsx("nav",{
                  className:"lm-dock-icons",
                  "aria-label":"核心功能矩阵",
                  children:dockItems.map(it=>e.jsxs(u,{
                    to:it.to,
                    navigate:r,
                    className:"lm-dock-item",
                    children:[
                      e.jsx("span",{
                        className:"lm-dock-icon-box",
                        children:e.jsx(it.Icon,{size:20,strokeWidth:1.65})
                      }),
                      e.jsx("span",{className:"lm-dock-label",children:it.label})
                    ]
                  },it.label))
                }),

                e.jsxs(u,{
                  to:"/wxq-lineups",
                  navigate:r,
                  className:"lm-start-cta",
                  children:[
                    e.jsxs("div",{
                      className:"lm-start-copy",
                      children:[
                        e.jsx("small",{children:"LINEUP PLAYBOOK // 74 NOTES"}),
                        e.jsx("span",{className:"lm-start-main",children:"实战阵容笔记"})
                      ]
                    }),
                    e.jsx("span",{className:"lm-start-bar"})
                  ]
                })
              ]
            })
          ]
        })
      })
    ]
  });
}

export{O as default};

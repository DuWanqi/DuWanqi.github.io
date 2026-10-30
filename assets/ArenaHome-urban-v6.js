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

  // Bottom-right minimalist floating icon dock (using official extracted WXQ icons)
  const dockItems=[
    {label:"棋手",to:"/players",iconSrc:"/assets/wxq-ui/icon5.webp"},
    {label:"卡牌",to:"/atlas",iconSrc:"/assets/wxq-ui/icon1.webp"},
    {label:"阵容",to:"/wxq-lineups",iconSrc:"/assets/wxq-ui/icon2.webp"},
    {label:"克制链",to:"/counters",iconSrc:"/assets/wxq-ui/icon4.webp"},
    {label:"数值研究",to:"/analysis/dps",iconSrc:"/assets/wxq-ui/icon6.webp"}
  ];

  // Top-left floating icon + liquid metal text strip (using official extracted WXQ icons)
  const topQuickLinks=[
    {label:"英雄图鉴",to:"/explore/hero-sulie",iconSrc:"/assets/wxq-ui/icon1.webp"},
    {label:"装备合成",to:"/explore/equipment-catalog",iconSrc:"/assets/wxq-ui/icon2.webp"},
    {label:"天赋词条",to:"/explore/talent-catalog",iconSrc:"/assets/wxq-ui/icon3.webp"},
    {label:"效果牌库",to:"/explore/effect-catalog",iconSrc:"/assets/wxq-ui/icon4.webp"},
    {label:"钻石狂潮",to:"/modes/diamond-frenzy?tab=packs",iconSrc:"/assets/wxq-ui/i-badge.png"},
    {label:"抽卡模拟",to:"/analysis/draw",iconSrc:"/assets/wxq-ui/i-badge2.png"}
  ];

  return e.jsxs("div",{
    className:"lm-home",
    children:[
      /* Background Layer: Official KV + Liquid Metal Stepped Ring */
      e.jsxs("div",{
        className:"lm-backdrop",
        "aria-hidden":"true",
        children:[
          e.jsx("img",{src:"/assets/official-kv.jpg",alt:""}),
          e.jsx("div",{className:"lm-vignette"}),
          e.jsx("div",{className:"lm-ring-graphic"})
        ]
      }),

      /* HUD Frame */
      e.jsxs("section",{
        className:"lm-hud",
        children:[
          /* Top Sub-HUD Bar: Official WXQ Icon + Floating Liquid Metal Text + Official Capsule Search */
          e.jsxs("div",{
            className:"lm-hud-top",
            children:[
              e.jsx("nav",{
                className:"lm-top-pills",
                "aria-label":"快速图鉴入口",
                children:topQuickLinks.map(item=>e.jsxs(u,{
                  to:item.to,
                  navigate:r,
                  className:"lm-top-pill",
                  children:[
                    e.jsx("img",{className:"lm-native-icon",src:item.iconSrc,alt:"","aria-hidden":"true"}),
                    e.jsx("span",{children:item.label})
                  ]
                },item.to))
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
              })
            ]
          }),

          /* Center Stage: Official Diagonal-Hatch Decoration + Liquid Metal Title */
          e.jsxs("div",{
            className:"lm-center-stage",
            children:[
              e.jsx("div",{className:"lm-chrome-tag",children:"CHAMPIONSHIP // TACTICAL NOTES"}),
              e.jsx("h1",{className:"lm-chrome-title",children:"万象棋笔记"})
            ]
          }),

          /* Bottom Bar: Left status line + Right Lobby Dock ("棋手 / 卡牌 / 阵容" + "实战阵容笔记|") */
          e.jsxs("div",{
            className:"lm-hud-bottom",
            children:[
              e.jsxs("div",{
                className:"lm-status-capsule",
                children:[
                  e.jsx("img",{className:"lm-status-badge",src:"/assets/wxq-ui/i-badge2.png",alt:""}),
                  e.jsx("span",{children:"【万象启程】74 篇实战阵容笔记 & 1,492 实体克制推演图谱已就绪"})
                ]
              }),

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
                          children:e.jsx("img",{src:it.iconSrc,alt:""})
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
                      e.jsx("span",{className:"lm-start-main",children:"实战阵容笔记"}),
                      e.jsx("span",{className:"lm-start-bar"})
                    ]
                  })
                ]
              })
            ]
          })
        ]
      })
    ]
  });
}

export{O as default};

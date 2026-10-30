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

  // Left-side circular Liquid Metal orbs (inspired by Wanxiangqi lobby "成长之路 / 战令 / 万象之都")
  const leftOrbs=[
    {val:"74",sub:"NOTES",label:"实战笔记",to:"/wxq-lineups"},
    {val:"86",sub:"HEROES",label:"英雄卡牌",to:"/explore/hero-sulie"},
    {val:"9.1k",sub:"GRAPH",label:"克制推演",to:"/counters"}
  ];

  // Bottom-right minimalist icon dock (inspired by Wanxiangqi lobby "棋手 / 卡牌 / 阵容 + 开始游戏")
  const dockItems=[
    {label:"棋手",to:"/players",Icon:w},
    {label:"卡牌",to:"/atlas",Icon:N},
    {label:"攻略笔记",to:"/playbooks/ali_zhadunyao",Icon:I},
    {label:"克制链",to:"/counters",Icon:z},
    {label:"木桩探测",to:"/analysis/dps",Icon:S}
  ];

  // Top-left minimalist quick bar (inspired by Wanxiangqi lobby top bar)
  const topQuickLinks=[
    {label:"英雄图鉴",to:"/explore/hero-sulie"},
    {label:"装备合成",to:"/explore/equipment-catalog"},
    {label:"天赋词条",to:"/explore/talent-catalog"},
    {label:"效果牌库",to:"/explore/effect-catalog"},
    {label:"钻石狂潮",to:"/modes/diamond-frenzy?tab=packs"},
    {label:"抽卡模拟",to:"/analysis/draw"}
  ];

  return e.jsxs("div",{
    className:"lm-home",
    children:[
      /* Background Layer: Official KV + Liquid Metal Stepped Ring SVG + Iridescent Orbs */
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
          /* Top Sub-HUD Bar */
          e.jsxs("div",{
            className:"lm-hud-top",
            children:[
              e.jsx("nav",{
                className:"lm-top-pills",
                "aria-label":"快速图鉴入口",
                children:topQuickLinks.map(item=>e.jsx(u,{
                  to:item.to,
                  navigate:r,
                  className:"lm-top-pill",
                  children:item.label
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

          /* Left Circular Liquid Metal Medallions (like 成长之路 / 战令 / 万象之都) */
          e.jsx("aside",{
            className:"lm-left-orbs",
            "aria-label":"核心数据徽章",
            children:leftOrbs.map(orb=>e.jsxs(u,{
              to:orb.to,
              navigate:r,
              className:"lm-orb",
              children:[
                e.jsxs("div",{
                  className:"lm-orb-circle",
                  children:[
                    e.jsx("strong",{children:orb.val}),
                    e.jsx("small",{children:orb.sub})
                  ]
                }),
                e.jsx("span",{className:"lm-orb-label",children:orb.label})
              ]
            },orb.label))
          }),

          /* Center-Left Liquid Chrome Championship Title */
          e.jsxs("div",{
            className:"lm-center-stage",
            children:[
              e.jsx("div",{className:"lm-chrome-tag",children:"CHAMPIONSHIP // TACTICAL NOTES"}),
              e.jsx("h1",{className:"lm-chrome-title",children:"万象棋笔记"})
            ]
          }),

          /* Bottom Bar: Left status capsule + Right Lobby Dock ("棋手 / 卡牌 / 阵容" + "实战阵容笔记") */
          e.jsxs("div",{
            className:"lm-hud-bottom",
            children:[
              e.jsxs("div",{
                className:"lm-status-capsule",
                children:[
                  e.jsx("i",{className:"lm-pulse"}),
                  e.jsx("span",{children:"S1 万象启程 · 74 篇实战阵容笔记 & 1,492 实体克制图谱已就绪"})
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
                          children:e.jsx(it.Icon,{size:19,strokeWidth:1.6})
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

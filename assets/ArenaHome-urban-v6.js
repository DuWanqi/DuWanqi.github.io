import{b as o,j as e,h as C}from"./card-image-preview-C175IomB.js";import"./chessplayerFacts-DL_9PpXO.js";import"./site-v7.js";import"./preload-helper-DMGCcr4D.js";

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
  const[bgMode,setBgMode]=o.useState("lobby"); // "lobby" | "kv"
  const k=s=>{s.preventDefault(),d?.(c.trim())};

  // 顶栏金色 3D 图标导航（100% 源自 08_局内HUD与大厅核心UI_UI_HUD_Lobby/UILobbyMainMenu_baike_*）
  const topGoldNav=[
    {label:"实战笔记",to:"/wxq-lineups",iconSrc:"/assets/wxq-lobby/icon_baike_46.png",orig:"活动"},
    {label:"装备合成",to:"/explore/equipment-catalog",iconSrc:"/assets/wxq-lobby/icon_baike_42.png",orig:"商城"},
    {label:"天赋词条",to:"/explore/talent-catalog",iconSrc:"/assets/wxq-lobby/icon_baike_23.png",orig:"祈愿"},
    {label:"效果牌库",to:"/explore/effect-catalog",iconSrc:"/assets/wxq-lobby/icon_baike_44.png",orig:"交易行"},
    {label:"抽卡模拟",to:"/analysis/draw",iconSrc:"/assets/wxq-lobby/icon_baike_53.png",orig:"礼盒"},
    {label:"钻石狂潮",to:"/modes/diamond-frenzy?tab=packs",iconSrc:"/assets/wxq-lobby/icon_baike_7.png",orig:"检索"}
  ];

  // 右下角纯白/亮银浮空操作台（1:1 对应游戏大厅右下角「棋手 / 卡牌 / 阵容」）
  const rightDockItems=[
    {
      label:"棋手",
      to:"/players",
      svg:e.jsx("svg",{viewBox:"0 0 32 32",fill:"none",children:e.jsx("path",{d:"M4 24L6.5 10L12.5 16L16 7L19.5 16L25.5 10L28 24H4ZM5.5 26.5H26.5V28.5H5.5V26.5Z",fill:"url(#wxqDockSilver)"})})
    },
    {
      label:"卡牌",
      to:"/atlas",
      iconSrc:"/assets/wxq-lobby/icon_baike_40.png",
      isSilverFilter:true
    },
    {
      label:"阵容",
      to:"/wxq-lineups",
      iconSrc:"/assets/wxq-lobby/icon_baike_48.png",
      isSilverFilter:true
    },
    {
      label:"克制链",
      to:"/counters",
      iconSrc:"/assets/wxq-lobby/icon_baike_39.png",
      isSilverFilter:true
    },
    {
      label:"木桩探测",
      to:"/analysis/dps",
      iconSrc:"/assets/wxq-lobby/icon_baike_1.png",
      isSilverFilter:true
    }
  ];

  return e.jsxs("div",{
    className:`wxq-lobby-home is-bg-${bgMode}`,
    children:[
      /* SVG 银白金属渐变定义 */
      e.jsx("svg",{
        width:0,height:0,style:{position:"absolute"},
        children:e.jsx("defs",{
          children:e.jsxs("linearGradient",{
            id:"wxqDockSilver",x1:"0%",y1:"0%",x2:"0%",y2:"100%",
            children:[
              e.jsx("stop",{offset:"0%",stopColor:"#ffffff"}),
              e.jsx("stop",{offset:"65%",stopColor:"#e5eefb"}),
              e.jsx("stop",{offset:"100%",stopColor:"#a9bdd8"})
            ]
          })
        })
      }),

      /* 1. 游戏大厅背景层：支持万象之都斑马线街道夜景 + 右侧巨型液态金属皇冠雕像（源自 09 Icon_PaiWei_10.png） */
      e.jsxs("div",{
        className:"wxq-lobby-backdrop",
        "aria-hidden":"true",
        children:[
          e.jsx("img",{
            className:"wxq-lobby-bg-img",
            src:bgMode==="lobby"?"/assets/wxq-ui/main-bg.jpg":"/assets/official-kv.jpg",
            alt:""
          }),
          e.jsx("div",{className:"wxq-lobby-crosswalk"}),
          e.jsx("div",{className:"wxq-lobby-vignette"}),
          /* 右侧液态金属皇冠主雕像（09_段位排位与MVP击杀高光 Icon_PaiWei_10.png 原厂解包大图） */
          bgMode==="lobby"&&e.jsxs("div",{
            className:"wxq-lobby-statue-wrap",
            children:[
              e.jsx("div",{className:"wxq-lobby-statue-glow"}),
              e.jsx("img",{
                className:"wxq-lobby-statue-img",
                src:"/assets/wxq-lobby/Icon_PaiWei_10.png",
                alt:""
              })
            ]
          })
        ]
      }),

      /* 2. 大厅 HUD 主画布（1:1 对齐客户端大厅布局） */
      e.jsxs("section",{
        className:"wxq-lobby-hud",
        children:[
          /* 顶栏：汉堡菜单 + 竖线 + 金色 3D 图标条 + 右侧胶囊检索框 */
          e.jsxs("header",{
            className:"wxq-lobby-topbar",
            children:[
              e.jsxs("div",{
                className:"wxq-topbar-left",
                children:[
                  e.jsxs("button",{
                    type:"button",
                    className:"wxq-hamburger-btn",
                    title:"切换大厅主视觉 (万象之都雕像 / 官方群像KV)",
                    onClick:()=>setBgMode(m=>m==="lobby"?"kv":"lobby"),
                    children:[
                      e.jsx("span",{}),
                      e.jsx("span",{}),
                      e.jsx("span",{})
                    ]
                  }),
                  e.jsx("span",{className:"wxq-topbar-divider"}),
                  e.jsx("nav",{
                    className:"wxq-gold-nav",
                    "aria-label":"大厅顶栏核心入口",
                    children:topGoldNav.map(item=>e.jsxs(u,{
                      to:item.to,
                      navigate:r,
                      className:"wxq-gold-nav-item",
                      children:[
                        e.jsx("img",{src:item.iconSrc,alt:""}),
                        e.jsx("span",{children:item.label})
                      ]
                    },item.to))
                  })
                ]
              }),

              e.jsxs("form",{
                className:"wxq-lobby-search",
                onSubmit:k,
                children:[
                  e.jsx(C,{size:15,"aria-hidden":"true"}),
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

          /* 左上角三大圆球入口（1:1 复刻截图「24 成长之路」「13 战令」「CITY 万象之都」） */
          e.jsxs("div",{
            className:"wxq-left-orbs",
            children:[
              /* 第 1 球：74 实战笔记（复刻「24 成长之路」：原厂 Circle.png + baike_25 六芒星皇冠 + 74） */
              e.jsxs(u,{
                to:"/wxq-lineups",
                navigate:r,
                className:"wxq-orb-item",
                children:[
                  e.jsxs("div",{
                    className:"wxq-orb-circle wxq-orb-silver",
                    children:[
                      e.jsx("img",{className:"wxq-orb-ring",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_Circle.png",alt:""}),
                      e.jsx("img",{className:"wxq-orb-saoguang",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_saoguang.png",alt:""}),
                      e.jsx("img",{className:"wxq-orb-emblem",src:"/assets/wxq-lobby/icon_baike_25.png",alt:""}),
                      e.jsx("span",{className:"wxq-orb-num",children:"74"})
                    ]
                  }),
                  e.jsx("span",{className:"wxq-orb-caption",children:"实战笔记"})
                ]
              }),

              /* 第 2 球：86 英雄图鉴（复刻「13 战令」：原厂 Circle.png + baike_57 战令金勋章 + 86） */
              e.jsxs(u,{
                to:"/explore/hero-sulie",
                navigate:r,
                className:"wxq-orb-item",
                children:[
                  e.jsxs("div",{
                    className:"wxq-orb-circle wxq-orb-silver",
                    children:[
                      e.jsx("img",{className:"wxq-orb-ring",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_Circle.png",alt:""}),
                      e.jsx("img",{className:"wxq-orb-saoguang",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_saoguang.png",alt:""}),
                      e.jsx("img",{className:"wxq-orb-emblem",src:"/assets/wxq-lobby/icon_baike_57.png",alt:""}),
                      e.jsx("span",{className:"wxq-orb-num",children:"86"})
                    ]
                  }),
                  e.jsx("span",{className:"wxq-orb-caption",children:"英雄图鉴"})
                ]
              }),

              /* 第 3 球：万象之都 CITY · 克制图谱（100% 原厂 6 层分层切图拼合！） */
              e.jsxs(u,{
                to:"/counters",
                navigate:r,
                className:"wxq-orb-item wxq-orb-city-item",
                children:[
                  e.jsxs("div",{
                    className:"wxq-orb-circle wxq-orb-city",
                    children:[
                      e.jsx("img",{className:"wxq-city-bg",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_cityBG.png",alt:""}),
                      e.jsx("img",{className:"wxq-city-caiguang",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_caiguang.png",alt:""}),
                      e.jsx("img",{className:"wxq-city-statue",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_xulieren_huangse01.png",alt:""}),
                      e.jsx("img",{className:"wxq-orb-ring",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_Circle.png",alt:""}),
                      e.jsx("img",{className:"wxq-city-text-fill",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_tianchong_zi.png",alt:""}),
                      e.jsx("img",{className:"wxq-city-text-stroke",src:"/assets/wxq-lobby/UILobbyCircleOperationEnter_WXC_TEX_miaobian_zi.png",alt:""})
                    ]
                  }),
                  e.jsx("span",{className:"wxq-orb-caption",children:"万象克制"})
                ]
              })
            ]
          }),

          /* 左侧中部：「排 行 —⇄—」极简折叠入口 + 半透明圆点（1:1 复刻截图左侧中部） */
          e.jsxs(u,{
            to:"/wxq-lineups",
            navigate:r,
            className:"wxq-left-rank-widget",
            title:"查看全分段热门阵容排行",
            children:[
              e.jsx("span",{className:"wxq-rank-title",children:"排 行"}),
              e.jsx("span",{className:"wxq-rank-arrows",children:"— ⇄ —"}),
              e.jsxs("div",{
                className:"wxq-rank-dots",
                children:[
                  e.jsx("span",{className:"wxq-rank-dot"}),
                  e.jsx("span",{className:"wxq-rank-dot"}),
                  e.jsx("span",{className:"wxq-rank-dot"})
                ]
              })
            ]
          }),

          /* 底部栏：左下角社交/招募广播栏 + 右下角「棋手/卡牌/阵容」+「实战笔记|」 */
          e.jsxs("footer",{
            className:"wxq-lobby-bottom",
            children:[
              /* 左下角：头像框 + 好友/社区图标 + 招募/更新广播条（1:1 复刻截图左下角） */
              e.jsxs("div",{
                className:"wxq-bottom-left-social",
                children:[
                  e.jsxs(u,{
                    to:"/players",
                    navigate:r,
                    className:"wxq-avatar-box",
                    title:"浏览全部棋手图鉴",
                    children:[
                      e.jsx("img",{className:"wxq-avatar-img",src:"/assets/wxq-lobby/Icon_LordHead_DaQiao_128x128.png",alt:"棋手"}),
                      e.jsx("span",{className:"wxq-avatar-sub",children:"棋手"})
                    ]
                  }),

                  e.jsxs("div",{
                    className:"wxq-social-bar",
                    children:[
                      e.jsx(u,{
                        to:"/explore/hero-sulie",
                        navigate:r,
                        className:"wxq-social-icon-btn",
                        title:"86 位英雄全图鉴",
                        children:e.jsx("img",{src:"/assets/wxq-lobby/icon_baike_39_1.png",alt:""})
                      }),
                      e.jsx("span",{className:"wxq-social-sep"}),
                      e.jsx(u,{
                        to:"/players",
                        navigate:r,
                        className:"wxq-social-icon-btn",
                        title:"棋手档案",
                        children:e.jsx("img",{src:"/assets/wxq-lobby/icon_baike_15.png",alt:""})
                      }),
                      e.jsx("span",{className:"wxq-social-sep"}),
                      e.jsxs(u,{
                        to:"/wxq-lineups",
                        navigate:r,
                        className:"wxq-chat-ticker",
                        children:[
                          e.jsx("img",{className:"wxq-chat-icon",src:"/assets/wxq-lobby/icon_baike_11.png",alt:""}),
                          e.jsx("span",{className:"wxq-chat-tag",children:"【万象启程】"}),
                          e.jsx("span",{className:"wxq-chat-text",children:"74 篇实战阵容笔记 & 9,289 张客户端原生图鉴已就绪"})
                        ]
                      })
                    ]
                  })
                ]
              }),

              /* 右下角：上排纯白图标（棋手·卡牌·阵容·克制链·木桩探测）+ 下排「实战笔记|」+ S1 万象启程 */
              e.jsxs("div",{
                className:"wxq-bottom-right-dock",
                children:[
                  e.jsx("nav",{
                    className:"wxq-dock-row",
                    "aria-label":"大厅右下角功能矩阵",
                    children:rightDockItems.map(it=>e.jsxs(u,{
                      to:it.to,
                      navigate:r,
                      className:"wxq-dock-btn",
                      children:[
                        e.jsx("span",{
                          className:`wxq-dock-icon-wrap ${it.isSilverFilter?"is-silver-icon":""}`,
                          children:it.svg?it.svg:e.jsx("img",{src:it.iconSrc,alt:""})
                        }),
                        e.jsx("span",{className:"wxq-dock-text",children:it.label})
                      ]
                    },it.label))
                  }),

                  e.jsxs(u,{
                    to:"/wxq-lineups",
                    navigate:r,
                    className:"wxq-start-game-btn",
                    children:[
                      e.jsxs("div",{
                        className:"wxq-start-main-row",
                        children:[
                          e.jsx("span",{className:"wxq-start-label",children:"实战笔记"}),
                          e.jsx("span",{className:"wxq-start-cursor"})
                        ]
                      }),
                      e.jsxs("div",{
                        className:"wxq-start-sub-row",
                        children:[
                          e.jsx("span",{className:"wxq-start-script",children:"Season 1 · Wanxiang"}),
                          e.jsx("span",{className:"wxq-start-season",children:"S1 万象启程"})
                        ]
                      })
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

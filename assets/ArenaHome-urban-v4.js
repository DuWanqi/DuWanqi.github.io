import{b as o,S as N,d as b,L as z,e as y,U as w,B as I,j as e,h as C,n as S,k as g,c as R}from"./card-image-preview-C175IomB.js";import{o as P}from"./chessplayerFacts-DL_9PpXO.js";import{h as W}from"./site-v7.js";import{H as _}from"./sponsor-link-BZ84tFe_.js?v=7";import"./preload-helper-DMGCcr4D.js";

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

function O({navigate:r,onSearch:d,phoneH5:l=!1}){
  const[c,h]=o.useState("");
  const k=s=>{s.preventDefault(),d?.(c.trim())};

  const workbenchModules=[
    {
      code:"01 // DPS ENGINE",
      title:"固定目标伤害计算",
      sub:"STRICT COMBAT SIMULATION",
      desc:"设置英雄等级、觉醒、3槽装备与木桩双抗，精确核验20秒内普攻、主动施法与装备附加伤害时间线及承伤/控制覆盖。",
      to:"/analysis/dps",
      altTo:"/lab",
      altLabel:"多英雄同台对比版 ↗",
      accent:"cyan"
    },
    {
      code:"02 // PLAYBOOK NOTES",
      title:"攻略笔记 · 26篇流派手册",
      sub:"ROUND-BY-ROUND TACTICS",
      desc:"收录阿离·伞曜炸盾、白歌·三分倒转刺、常小娥·海陆空等26篇高分段逐回合过渡、成型、装备路线与7×4站位。",
      to:"/playbooks/ali_zhadunyao",
      accent:"gold"
    },
    {
      code:"03 // LINEUP ARCHIVE",
      title:"社区阵容库 · 4266套编成",
      sub:"META LINEUP REPOSITORY",
      desc:"聚合营地推荐榜与热门榜去重数据，支持12大体系与20位棋手交叉筛选，含完整站位棋盘、配装与一键复制阵容码。",
      to:"/wxq-lineups",
      altTo:"/lineups",
      altLabel:"阵容推演室 ↗",
      accent:"cyan"
    },
    {
      code:"04 // COUNTER MATRIX",
      title:"流派克制链 · 27×27矩阵",
      sub:"MATCHUP & MECHANIC EVIDENCE",
      desc:"基于官方卡面机制、社区高分实战与数值推演，拆解27大主流体系的55条克制关系与10条通用反制点。",
      to:"/counters",
      accent:"gold"
    }
  ];

  const atlasShortcuts=[
    {code:"CAT-01",label:"英雄图鉴",meta:`${W.categories.hero.count} 名英雄 · 技能/成长`,to:"/explore/hero-sulie",Icon:N},
    {code:"CAT-02",label:"装备图鉴",meta:"95 件装备 · 合成/收益",to:"/explore/equipment-catalog",Icon:b},
    {code:"CAT-03",label:"天赋图鉴",meta:"297 项天赋 · 轮次/互斥",to:"/explore/talent-catalog",Icon:z},
    {code:"CAT-04",label:"效果牌图鉴",meta:"98 张效果牌 · 衍生/来源",to:"/explore/effect-catalog",Icon:y},
    {code:"CAT-05",label:"棋手档案",meta:`${P.length} 位棋手 · 秘技/专属`,to:"/players",Icon:w},
    {code:"CAT-06",label:"机制词典",meta:"27 项核心词条与结算规则",to:"/mechanics",Icon:I},
    {code:"CAT-07",label:"钻石狂潮",meta:"卡包、拍卖轮次与特殊事件",to:"/modes/diamond-frenzy?tab=packs",Icon:y},
    {code:"CAT-08",label:"装备价值与抽卡",meta:"成装收益对比 / 商店刷牌模拟",to:"/analysis/equipment-value",Icon:S}
  ];

  const showcaseCards=[
    {
      name:"李白",
      role:"河洛 · 4阶 · 刺客",
      stat:"ATK 130% · 剑影不可选中",
      img:"/assets/official/2026-09-29/c9cc1a3e0e164414f72f29e955a09ad470f1a6caff49b88769d4ac10da1fb9a5.webp",
      to:"/explore/hero-libai"
    },
    {
      name:"孙尚香",
      role:"三分之地 · 3阶 · 射手",
      stat:"登场增益 · 贯穿爆发",
      img:"/assets/official/2026-09-29/de2818d013701fc4404df05aff68399f3fc399ef2f26746336dd91d1afd4b004.webp",
      to:"/explore/hero-sunshangxiang"
    },
    {
      name:"无尽巨剑",
      role:"铸成物理装 · 核心暴击",
      stat:"CRIT +30% · DMG +60%",
      img:"/assets/official/2026-09-29/ae9ae36a9ee6eb4a2ea6d1ece0929a550dd71cdd0dc0c6f418c22af372072443.webp",
      to:"/explore/equipment-catalog"
    }
  ];

  const metrics=[
    {label:"公开英雄档案",val:"86",unit:"HEROES",to:"/explore/hero-sulie"},
    {label:"装备与合成链",val:"95",unit:"EQUIPMENTS",to:"/explore/equipment-catalog"},
    {label:"天赋与效果牌",val:"395",unit:"CARDS",to:"/explore/talent-catalog"},
    {label:"流派攻略笔记",val:"26",unit:"NOTES",to:"/playbooks/ali_zhadunyao"},
    {label:"社区实战阵容",val:"4,266",unit:"LINEUPS",to:"/wxq-lineups"},
    {label:"克制关系矩阵",val:"27×27",unit:"COUNTERS",to:"/counters"}
  ];

  return e.jsx("div",{
    className:`arena-home urban-tech-home${l?" is-mobile-home":""}`,
    children:e.jsxs("div",{
      className:"ut-workspace",
      children:[
        e.jsxs("div",{
          className:"ut-status-bar",
          children:[
            e.jsxs("div",{
              className:"ut-status-left",
              children:[
                e.jsx("span",{className:"ut-tag-cyan",children:"WANXIANGQI // TACTICAL OS"}),
                e.jsx("span",{children:"王者万象棋 · 现代都市战术数据工作台"}),
                e.jsx("span",{className:"ut-sep",children:"/"}),
                e.jsx("span",{children:"STRICT COMBAT ANALYTICS"})
              ]
            }),
            e.jsxs("div",{
              className:"ut-status-right",
              children:[
                e.jsx("i",{className:"ut-dot"}),
                e.jsx("span",{children:"5,518 LOCAL ASSETS · ENGINE READY"})
              ]
            })
          ]
        }),

        e.jsxs("section",{
          className:"ut-hero-grid",
          children:[
            e.jsxs("div",{
              className:"ut-hero-main",
              children:[
                e.jsx("p",{className:"ut-eyebrow",children:"KING OF GLORY · WANXIANG CHESS WORKBENCH"}),
                e.jsx("h1",{className:"ut-title",children:"万象棋知识站"}),
                e.jsx("p",{
                  className:"ut-subtitle",
                  children:"用数据拆万象棋，用逻辑讲上分。集合固定木桩伤害推演、26篇逐回合流派攻略笔记、4266套社区阵容与27流派克制链矩阵。"
                }),
                e.jsxs("form",{
                  className:"ut-search-form",
                  onSubmit:k,
                  children:[
                    e.jsx(C,{size:18,"aria-hidden":"true"}),
                    e.jsx("input",{
                      value:c,
                      onChange:s=>h(s.target.value),
                      placeholder:"搜索英雄、装备、天赋、效果牌、机制关键词…",
                      "aria-label":"搜索万象棋知识站"
                    }),
                    e.jsx("button",{type:"submit",children:"搜索资料"})
                  ]
                }),
                e.jsxs("div",{
                  className:"ut-quick-actions",
                  children:[
                    e.jsxs(u,{
                      to:"/analysis/dps",
                      navigate:r,
                      className:"ut-btn ut-btn-primary",
                      children:[e.jsx(S,{size:16,strokeWidth:1.6}),"固定目标伤害",e.jsx(g,{size:15})]
                    }),
                    e.jsxs(u,{
                      to:"/playbooks/ali_zhadunyao",
                      navigate:r,
                      className:"ut-btn",
                      children:["攻略笔记 (26篇)",e.jsx(g,{size:15})]
                    }),
                    e.jsxs(u,{
                      to:"/wxq-lineups",
                      navigate:r,
                      className:"ut-btn",
                      children:[e.jsx(R,{size:16,strokeWidth:1.6}),"阵容库 (4266)",e.jsx(g,{size:15})]
                    }),
                    e.jsxs(u,{
                      to:"/counters",
                      navigate:r,
                      className:"ut-btn",
                      children:["流派克制链",e.jsx(g,{size:15})]
                    }),
                    e.jsxs(u,{
                      to:"/lab",
                      navigate:r,
                      className:"ut-btn",
                      children:["多英雄木桩对比",e.jsx(g,{size:15})]
                    })
                  ]
                })
              ]
            }),

            e.jsxs("div",{
              className:"ut-hero-showcase",
              "aria-label":"精选卡面陈列",
              children:[
                e.jsxs("div",{
                  className:"ut-showcase-head",
                  children:[
                    e.jsx("span",{children:"VERIFIED SPECIMENS // ARCHIVE"}),
                    e.jsx(u,{to:"/atlas",navigate:r,children:"进入万象图鉴 ↗"})
                  ]
                }),
                e.jsx("div",{
                  className:"ut-showcase-cards",
                  children:showcaseCards.map((card,idx)=>e.jsxs(u,{
                    to:card.to,
                    navigate:r,
                    className:`ut-specimen-card is-slot-${idx}`,
                    children:[
                      e.jsx("div",{
                        className:"ut-specimen-img",
                        children:e.jsx("img",{src:card.img,alt:card.name,loading:"eager"})
                      }),
                      e.jsxs("div",{
                        className:"ut-specimen-meta",
                        children:[
                          e.jsx("small",{children:card.role}),
                          e.jsx("strong",{children:card.name}),
                          e.jsx("em",{children:card.stat})
                        ]
                      })
                    ]
                  },card.name))
                })
              ]
            })
          ]
        }),

        e.jsx("section",{
          className:"ut-metrics-bar",
          "aria-label":"核心数据规模",
          children:metrics.map(m=>e.jsxs(u,{
            to:m.to,
            navigate:r,
            className:"ut-metric-cell",
            children:[
              e.jsx("span",{children:m.label}),
              e.jsxs("div",{
                children:[
                  e.jsx("strong",{children:m.val}),
                  e.jsx("small",{children:m.unit})
                ]
              })
            ]
          },m.label))
        }),

        e.jsxs("section",{
          className:"ut-section",
          children:[
            e.jsxs("header",{
              className:"ut-section-head",
              children:[
                e.jsxs("div",{
                  children:[
                    e.jsx("span",{children:"CORE TACTICAL WORKBENCH // 01 - 04"}),
                    e.jsx("h2",{children:"实战推演与数值工作区"})
                  ]
                }),
                e.jsx("p",{children:"固定木桩严谨数值推演、26篇逐回合流派攻略笔记、4266套社区阵容与27流派克制链矩阵"})
              ]
            }),
            e.jsx("div",{
              className:"ut-module-grid",
              children:workbenchModules.map(mod=>e.jsxs("article",{
                className:`ut-module-card is-${mod.accent}`,
                children:[
                  e.jsxs("div",{
                    className:"ut-module-top",
                    children:[
                      e.jsx("span",{className:"ut-module-code",children:mod.code}),
                      e.jsx("small",{children:mod.sub})
                    ]
                  }),
                  e.jsx("h3",{
                    children:e.jsx(u,{to:mod.to,navigate:r,children:mod.title})
                  }),
                  e.jsx("p",{children:mod.desc}),
                  e.jsxs("div",{
                    className:"ut-module-foot",
                    children:[
                      e.jsxs(u,{
                        to:mod.to,
                        navigate:r,
                        className:"ut-module-enter",
                        children:["进入工作区",e.jsx(g,{size:14})]
                      }),
                      mod.altTo&&e.jsx(u,{
                        to:mod.altTo,
                        navigate:r,
                        className:"ut-module-alt",
                        children:mod.altLabel
                      })
                    ]
                  })
                ]
              },mod.code))
            })
          ]
        }),

        e.jsxs("section",{
          className:"ut-section",
          children:[
            e.jsxs("header",{
              className:"ut-section-head",
              children:[
                e.jsxs("div",{
                  children:[
                    e.jsx("span",{children:"DATABASE INDEX // 01 - 08"}),
                    e.jsx("h2",{children:"万象图鉴与规则档案"})
                  ]
                }),
                e.jsx(u,{to:"/atlas",navigate:r,className:"ut-head-link",children:"查看完整万象图鉴目录 →"})
              ]
            }),
            e.jsx("div",{
              className:"ut-atlas-grid",
              children:atlasShortcuts.map(item=>e.jsxs(u,{
                to:item.to,
                navigate:r,
                className:"ut-atlas-cell",
                children:[
                  e.jsxs("div",{
                    className:"ut-atlas-cell-top",
                    children:[
                      e.jsx("span",{children:item.code}),
                      e.jsx(item.Icon,{size:16,strokeWidth:1.5})
                    ]
                  }),
                  e.jsx("strong",{children:item.label}),
                  e.jsx("small",{children:item.meta})
                ]
              },item.code))
            })
          ]
        }),

      ]
    })
  });
}

export{O as default};

# campaign 模版库

按 GTM 场景分的四套模版,每套 = `scoring-prompt.md`(LLM 打分标准)+ `config.json`
(报告排版配置)。挑一个最接近你场景的,整套复制出去,把标着 **【填空】** 的地方
换成你的真实信息即可:

```bash
cp -r campaigns/templates/customer-discovery campaigns/my-campaign
```

| 模版 | 场景 | 典型问题 |
|---|---|---|
| `customer-discovery/` | 找潜在客户 / 早期用户 | 谁会买我们的产品?谁会第一批用? |
| `kol-launch/` | 产品发布找传播者 | 发布日谁转发/评测最有用? |
| `investor-scan/` | 找投资人 | 这个圈子里谁投我们这个阶段、这个方向? |
| `talent-scan/` | 招聘 mapping | 我们要招的方向上,圈内有哪些人? |

三条铁律(每套模版里都写了,别删):

1. **公司背景先做事实核查**——只写有来源的说法,来源写进 `config.json` 的
   `sources_note`。名单会被拿去真实外联,错一句话跟着每次转发扩散。
2. **tier 判据写成可从 bio 判定的条件**,不写「知名」「有影响力」这类查无实据的形容词。
3. prompt 里的 category key 必须和 `config.json` 的 `categories[].key` 一一对应。

完整跑法见 `campaigns/README.md`;从零开始的教程见 `docs/GTM-COOKBOOK.md`。

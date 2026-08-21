import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  LineChart,
  Row,
  Stack,
  Stat,
  Table,
  Text,
} from "cursor/canvas";

const DATES = ["8/14", "8/15", "8/16", "8/17", "8/18", "8/19", "8/20", "8/21"];

const ALL_ROWS: Array<{
  mid: string;
  unit: string;
  final: string;
  peak: string;
  trough: string;
  last2: string;
  pattern: string;
  tone?: "success" | "danger" | "warning" | "info" | "neutral";
}> = [
  { mid: "M0058", unit: "2043", final: "+18,400", peak: "+18,400", trough: "−400", last2: "+3,000", pattern: "階段積み上げ（ピーク更新中）", tone: "success" },
  { mid: "M0067", unit: "2052", final: "+13,500", peak: "+14,000", trough: "−1,000", last2: "+1,200", pattern: "安定積み上げ", tone: "success" },
  { mid: "M0078", unit: "2127", final: "+13,200", peak: "+14,000", trough: "−2,200", last2: "+400", pattern: "後半二段爆発", tone: "success" },
  { mid: "M0054", unit: "2039", final: "+12,900", peak: "+14,600", trough: "−1,600", last2: "+700", pattern: "初日爆発を維持", tone: "success" },
  { mid: "M0044", unit: "2029", final: "+12,100", peak: "+13,100", trough: "−1,700", last2: "+750", pattern: "高ボラ積み上げ", tone: "success" },
  { mid: "M0080", unit: "2129", final: "+12,000", peak: "+12,000", trough: "−1,000", last2: "+1,050", pattern: "安定積み上げ", tone: "success" },
  { mid: "M0038", unit: "2023", final: "+11,300", peak: "+14,500", trough: "−1,200", last2: "−900", pattern: "ピーク後冷却", tone: "warning" },
  { mid: "M0068", unit: "2053", final: "+11,200", peak: "+12,100", trough: "−1,000", last2: "−400", pattern: "単日爆発を維持", tone: "success" },
  { mid: "M0033", unit: "2018", final: "+11,000", peak: "+12,700", trough: "0", last2: "+300", pattern: "階段積み上げ", tone: "success" },
  { mid: "M0040", unit: "2025", final: "+10,800", peak: "+11,300", trough: "−1,400", last2: "+300", pattern: "後半爆発", tone: "success" },
  { mid: "M0079", unit: "2128", final: "+10,500", peak: "+14,900", trough: "−3,600", last2: "−1,250", pattern: "ピーク後冷却", tone: "warning" },
  { mid: "M0070", unit: "2055", final: "+10,200", peak: "+14,400", trough: "−1,900", last2: "−1,750", pattern: "ピーク後冷却", tone: "warning" },
  { mid: "M0057", unit: "2042", final: "+7,500", peak: "+7,900", trough: "−2,600", last2: "+2,600", pattern: "高ボラ", tone: "info" },
  { mid: "M0042", unit: "2027", final: "+7,400", peak: "+7,400", trough: "−800", last2: "+1,050", pattern: "高ボラ", tone: "info" },
  { mid: "M0052", unit: "2037", final: "+6,800", peak: "+7,100", trough: "−4,900", last2: "−150", pattern: "後半爆発", tone: "info" },
  { mid: "M0031", unit: "2016", final: "+6,100", peak: "+10,400", trough: "0", last2: "−700", pattern: "初日爆発後に失速", tone: "warning" },
  { mid: "M0043", unit: "2028", final: "+6,100", peak: "+10,500", trough: "−1,600", last2: "−900", pattern: "初日爆発後に失速", tone: "warning" },
  { mid: "M0075", unit: "2124", final: "+5,300", peak: "+6,500", trough: "−1,700", last2: "+850", pattern: "安定寄り", tone: "info" },
  { mid: "M0039", unit: "2024", final: "+4,800", peak: "+8,200", trough: "−1,100", last2: "−1,050", pattern: "ピーク後冷却", tone: "warning" },
  { mid: "M0071", unit: "2056", final: "+4,600", peak: "+8,100", trough: "−2,300", last2: "−1,100", pattern: "混合", tone: "neutral" },
  { mid: "M0036", unit: "2021", final: "+4,400", peak: "+7,500", trough: "−4,700", last2: "−400", pattern: "高ボラ上昇", tone: "info" },
  { mid: "M0048", unit: "2033", final: "+2,900", peak: "+8,200", trough: "−2,400", last2: "−1,250", pattern: "単日爆発後失速", tone: "warning" },
  { mid: "M0073", unit: "2058", final: "+2,700", peak: "+3,900", trough: "−3,800", last2: "−600", pattern: "高ボラ", tone: "neutral" },
  { mid: "M0065", unit: "2050", final: "+2,000", peak: "+6,400", trough: "−600", last2: "−1,000", pattern: "山型・失速", tone: "warning" },
  { mid: "M0069", unit: "2054", final: "+1,100", peak: "+3,300", trough: "−2,300", last2: "+50", pattern: "中立", tone: "neutral" },
  { mid: "M0032", unit: "2017", final: "+800", peak: "+7,200", trough: "−2,300", last2: "−350", pattern: "山型・失速", tone: "warning" },
  { mid: "M0053", unit: "2038", final: "−200", peak: "+3,900", trough: "−2,000", last2: "−450", pattern: "中立", tone: "neutral" },
  { mid: "M0047", unit: "2032", final: "−900", peak: "+2,500", trough: "−9,200", last2: "−550", pattern: "単日V字（その後再失速）", tone: "warning" },
  { mid: "M0063", unit: "2048", final: "−1,500", peak: "+1,300", trough: "−3,700", last2: "+250", pattern: "中立", tone: "neutral" },
  { mid: "M0074", unit: "2059", final: "−1,500", peak: "+3,100", trough: "−2,300", last2: "−350", pattern: "混合", tone: "neutral" },
  { mid: "M0049", unit: "2034", final: "−1,600", peak: "+8,700", trough: "−1,600", last2: "−2,200", pattern: "山型・吐き出し", tone: "danger" },
  { mid: "M0034", unit: "2019", final: "−1,900", peak: "+2,800", trough: "−4,800", last2: "−1,900", pattern: "混合", tone: "neutral" },
  { mid: "M0072", unit: "2057", final: "−1,900", peak: "−100", trough: "−7,500", last2: "+1,450", pattern: "高ボラ", tone: "neutral" },
  { mid: "M0077", unit: "2126", final: "−2,000", peak: "+1,700", trough: "−3,600", last2: "−250", pattern: "混合", tone: "neutral" },
  { mid: "M0059", unit: "2044", final: "−2,100", peak: "+1,600", trough: "−6,300", last2: "+1,000", pattern: "回復途中", tone: "info" },
  { mid: "M0037", unit: "2022", final: "−2,500", peak: "+200", trough: "−7,200", last2: "0", pattern: "底打ち回復途中", tone: "info" },
  { mid: "M0064", unit: "2049", final: "−2,500", peak: "+500", trough: "−7,000", last2: "+550", pattern: "回復途中", tone: "info" },
  { mid: "M0056", unit: "2041", final: "−2,600", peak: "+3,600", trough: "−5,600", last2: "+550", pattern: "混合", tone: "neutral" },
  { mid: "M0061", unit: "2046", final: "−3,300", peak: "−100", trough: "−6,200", last2: "−150", pattern: "混合", tone: "neutral" },
  { mid: "M0076", unit: "2125", final: "−3,800", peak: "+1,800", trough: "−3,800", last2: "−1,200", pattern: "連日削り寄り", tone: "danger" },
  { mid: "M0035", unit: "2020", final: "−4,200", peak: "+2,700", trough: "−4,200", last2: "−1,700", pattern: "連日削り", tone: "danger" },
  { mid: "M0050", unit: "2035", final: "−5,700", peak: "−200", trough: "−5,700", last2: "−900", pattern: "連日削り", tone: "danger" },
  { mid: "M0046", unit: "2031", final: "−6,800", peak: "−100", trough: "−8,600", last2: "+300", pattern: "連日削り（末回復）", tone: "danger" },
  { mid: "M0066", unit: "2051", final: "−6,800", peak: "+1,800", trough: "−9,900", last2: "+350", pattern: "深沈み後回復途中", tone: "danger" },
  { mid: "M0041", unit: "2026", final: "−6,900", peak: "+900", trough: "−7,200", last2: "−350", pattern: "連日削り", tone: "danger" },
  { mid: "M0051", unit: "2036", final: "−6,900", peak: "−200", trough: "−11,100", last2: "+1,650", pattern: "深沈み後回復途中", tone: "danger" },
  { mid: "M0055", unit: "2040", final: "−10,600", peak: "−200", trough: "−14,300", last2: "+1,000", pattern: "連日削り", tone: "danger" },
  { mid: "M0060", unit: "2045", final: "−11,600", peak: "−200", trough: "−11,600", last2: "−1,450", pattern: "連日削り（低ボラ）", tone: "danger" },
  { mid: "M0062", unit: "2047", final: "−15,500", peak: "+300", trough: "−15,500", last2: "−1,500", pattern: "連日削り", tone: "danger" },
  { mid: "M0045", unit: "2030", final: "−16,900", peak: "−100", trough: "−16,900", last2: "−1,900", pattern: "連日削り", tone: "danger" },
];

export default function MagiarekoChainedByMachine() {
  return (
    <Stack gap={24}>
      <Stack gap={6}>
        <H1>L マギアレコード 台別累積スランプ</H1>
        <Text tone="secondary">
          エスパス日拓秋葉原駅前店（store 100928 / model_id 2）· 2026-08-14〜08-21 · 50台 ·
          連続スランプ（日跨ぎ平行移動）の期末差枚相当
        </Text>
        <Text tone="tertiary" size="small">
          Source: data/slump/100928/2/series/chained.csv および
          02_chained_by_machine の台別PNG。8/21は当日途中（平均系列は13:20時点）のため、直近1日は未確定。
        </Text>
      </Stack>

      <Row gap={24} wrap>
        <Stat value="+1,788" label="50台平均の期末累積（枚）" />
        <Stat value="+1,100" label="中央値（枚）" />
        <Stat value="12 / 50" label="期末 +1万枚以上" tone="success" />
        <Stat value="4 / 50" label="期末 −1万枚以下" tone="danger" />
      </Row>

      <Callout tone="info" title="全体は「平均付近」ではなく二極化">
        期末累積の平均は +1,788 枚だが、中央値は +1,100、+1万超えが12台・−1万割れが4台ある。
        少数の大勝ち台が平均を引き上げ、同じ島でも連日削られる台が並行している。
        機種全体の「今熱い／冷えている」より、台ごとの軌跡の型の方が説明力が高い。
      </Callout>

      <Grid columns={2} gap={20}>
        <Stack gap={8}>
          <H3>期末累積の分布（台数）</H3>
          <BarChart
            categories={["+1万以上", "+5千〜1万", "0〜+5千", "0〜−5千", "−5千〜−1万", "−1万以下"]}
            series={[{ name: "台数", data: [12, 6, 8, 15, 5, 4], tone: "info" }]}
            height={220}
            valueSuffix="台"
            showValues
          />
          <Text tone="tertiary" size="small">
            期末 chained_slump_value。0近傍（±5千）が23台で最多だが、右裾・左裾が厚い。
          </Text>
        </Stack>
        <Stack gap={8}>
          <H3>島別の期末平均</H3>
          <BarChart
            categories={["2016–2059島（44台）", "2124–2129島（6台）"]}
            series={[{ name: "期末平均（枚）", data: [1232, 5867], tone: "info" }]}
            height={220}
            valueSuffix=" 枚"
            showValues
          />
          <Text tone="tertiary" size="small">
            2124島は M0078 / M0079 / M0080 の3台が +1万超え。同じ6台でも M0076 は −3,800 まで沈んでいる。
          </Text>
        </Stack>
      </Grid>

      <Stack gap={8}>
        <H2>代表台の日次期末累積</H2>
        <Text tone="secondary">
          各日の最終サンプルの連続差枚。横軸は遊技日、縦軸は枚。ゼロは損益分岐ではなく「その日の起点からの連結位置」。
        </Text>
        <LineChart
          categories={DATES}
          series={[
            { name: "M0058 / 2043 階段積み上げ", data: [2200, 7400, 12200, 11700, 12000, 12200, 18200, 18400], tone: "success" },
            { name: "M0067 / 2052 安定積み上げ", data: [-500, 0, 4300, 6000, 9700, 11100, 12700, 13500], tone: "info" },
            { name: "M0078 / 2127 後半爆発", data: [-800, 100, -1800, 4300, 5000, 12300, 13100, 13200] },
            { name: "M0049 / 2034 山型吐き出し", data: [8200, 7200, 6300, 4600, 1700, 2500, -1200, -1600], tone: "warning" },
            { name: "M0045 / 2030 連日削り", data: [-4100, -7700, -9500, -12000, -11700, -13400, -15500, -16900], tone: "danger" },
          ]}
          height={280}
          beginAtZero={false}
          valueSuffix=" 枚"
          referenceLines={[{ value: 0, label: "0", tone: "neutral" }]}
        />
        <Text tone="tertiary" size="small">
          Source: chained.csv の日次最終 chained_slump_value · 2026-08-14〜08-21
        </Text>
      </Stack>

      <Divider />

      <H2>型ごとの台別考察</H2>
      <Text>
        連続グラフから読めるのは「設定」そのものではなく、この8日間に差枚がどう積まれたか、である。
        マギアレコードは AT の当たり日が1〜2日あると累積が大きく跳ね、外れが続くとほぼ直線で沈む。
        その二型が島内で同時に出ている。
      </Text>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader trailing="+18,400 枚">M0058 / 2043番 · 階段積み上げ</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                8/14–16 で +2,200 → +5,000 → +4,700 と連続プラス。8/17–19 はほぼ横ばい（+12,000 付近の台地）のあと、
                8/20 に再び +6,000。期末は期間ピークそのもので、押し目を作らず高値圏を維持している。
              </Text>
              <Text tone="secondary" size="small">
                日次終値: +2200, +5000, +4700, −500, +300, +200, +6000, 0
              </Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing="+13,500 / +12,000 枚">M0067・M0080 · 安定積み上げ</CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                2052番（M0067）は8日中7日プラス。序盤はゼロ付近でもたつき、8/16 から右肩上がりが定着。
                ボラティリティ（日次終値の標準偏差 1,459）は勝ち台の中で小さい。
              </Text>
              <Text>
                2129番（M0080）も7日プラスで期末がピーク。大きな単日爆発なしに +12,000 まで積んでいる。
                「当たり日待ち」ではなく、毎日少しずつ上に乗る型。
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader trailing="+13,200 枚">M0078 / 2127番 · 後半二段爆発</CardHeader>
          <CardBody>
            <Text>
              8/14–16 はゼロ〜マイナスでもたつき、8/17 に +6,300、8/19 に +7,100。
              グラフ上は 30時間付近まで横ばい、その後二段の急勾配。2124島の牽引役で、
              隣の M0079（2128）も 8/18 に +9,100 を出しているが、こちらはピーク後に吐いている。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing="+12,900 枚">M0054 / 2039番 · 初日爆発を維持</CardHeader>
          <CardBody>
            <Text>
              8/14 だけで +9,200。その後は凸凹だが累積を大きく吐き出さず、8/17 と 8/20 に再加速。
              8/21 途中は −1,700 と失速気味で、ピーク +14,600 から約 1,700 枚のドローダウン。
              「当たったあと沈む」山型ではなく、高値圏で保っている。
            </Text>
          </CardBody>
        </Card>
      </Grid>

      <H3>ピーク後に冷えている勝ち台 — 期末プラスでも直近は逆方向</H3>
      <Text>
        期末 +1万超えでも、直近2日平均がマイナスの台が4台ある。累積の見た目は「まだ熱い」が、
        グラフの右端はすでに下り坂。昨日までの残高を今日の期待値と混同しない方がよい。
      </Text>
      <Table
        headers={["台", "番号", "期末", "ピーク", "ピークからの下落", "直近2日平均", "読み"]}
        columnAlign={["left", "right", "right", "right", "right", "right", "left"]}
        rows={[
          ["M0038", "2023", "+11,300", "+14,500", "3,200", "−900", "8/16–17 で急騰、8/18 以降は下り"],
          ["M0079", "2128", "+10,500", "+14,900", "4,400", "−1,250", "8/18 の +9,100 がピーク。以降3日マイナス"],
          ["M0070", "2055", "+10,200", "+14,400", "4,200", "−1,750", "8/19 まで積み、8/20–21 で吐き出し"],
          ["M0068", "2053", "+11,200", "+12,100", "900", "−400", "8/16 の +8,200 依存。直近は小幅マイナス"],
        ]}
        rowTone={["warning", "warning", "warning", "warning"]}
        striped
      />

      <H3>山型・単日爆発のあとゼロを割る台</H3>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <Text weight="semibold">M0049 / 2034番 · 山型の典型</Text>
          <Text>
            8/14 に +8,200 で期間ピーク。以降ほぼ毎日マイナスで、8/20 にゼロを割り期末 −1,600。
            ピークからの下落は 10,300 枚。グラフは「当たった初日のあと、6日間かけて全額以上を返す」形。
          </Text>
          <Text weight="semibold">M0048 / 2033番</Text>
          <Text>
            8/15 に +10,000。その1日以外はすべてマイナスで、残高は +8,200 → +2,900 まで縮小。
            まだプラス圏だが、軌跡は M0049 と同じ「単日依存の下り坂」。
          </Text>
        </Stack>
        <Stack gap={8}>
          <Text weight="semibold">M0047 / 2032番 · 単日V字</Text>
          <Text>
            8/14–17 で −8,700 まで沈み、8/18 に +10,800 で一気に +2,200 まで戻す。
            その後また失速し期末 −900。ボラティリティは全台最大級（日次終値 σ=4,317）。
            「沈み切ったあとの大当たり」は起きるが、その翌日以降は再びマイナス側。
          </Text>
          <Text weight="semibold">同じ山型の周辺</Text>
          <Text>
            M0031（2016, 初日 +6,200 → 期末 +6,100）、M0032（2017, 初日 +5,800 → 期末 +800）、
            M0043（2028, 初日2日で約 +10,000 → 期末 +6,100）、M0065（2050, 初日 +5,100 → 期末 +2,000）。
            2016番台の端は「序盤に当たって後半吐く」が集中している。
          </Text>
        </Stack>
      </Grid>

      <H3>連日削り — 回復のない直線下降</H3>
      <Text>
        プラス日が0〜1日しかなく、連続グラフがほぼ右肩下がり。AT の当たり日がこの期間に乗らなかった型。
        下落速度は台によって違い、M0060 は毎日 −1,000〜−2,000 の低ボラ削り、M0062 / M0045 はより急。
      </Text>
      <BarChart
        categories={["2030 M0045", "2047 M0062", "2045 M0060", "2040 M0055", "2026 M0041", "2036 M0051", "2031 M0046", "2051 M0066"]}
        series={[{ name: "期末累積（枚）", data: [-16900, -15500, -11600, -10600, -6900, -6900, -6800, -6800], tone: "danger" }]}
        height={240}
        beginAtZero={false}
        valueSuffix=" 枚"
        showValues
        referenceLines={[{ value: 0, label: "0", tone: "neutral" }]}
      />
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <Text weight="semibold">M0045 / 2030番 · 最弱</Text>
          <Text>
            8日中プラスは 8/18 の +300 のみ。グラフはほぼ一直線に −16,900。
            小幅な戻り（8/17 終盤、8/19 冒頭）は翌日に打ち消される。
          </Text>
          <Text weight="semibold">M0062 / 2047番</Text>
          <Text>
            傾きが最も急（時間あたり約 −256 枚）。8/14 にわずかにプラス圏へ出たあと、二度と戻らない。
            8/19 の +300 も翌日以降で消える。
          </Text>
        </Stack>
        <Stack gap={8}>
          <Text weight="semibold">M0060 / 2045番 · 低ボラの連敗</Text>
          <Text>
            プラス日ゼロ。日次終値のばらつきは全台最小級（σ=587）。毎日同じ幅で削られる。
            「大きく負ける日」がない代わりに、戻る日もない。
          </Text>
          <Text weight="semibold">沈みからの戻り途中</Text>
          <Text>
            M0051（2036）は −11,100 まで沈んだあと 8/20 に +3,200。M0066（2051）も終盤2日がプラス。
            ただし期末はまだ −6,800〜−6,900 で、V字完成ではない。
          </Text>
        </Stack>
      </Grid>

      <H3>高ボラ混合 — 当たり日と外れ日が交互</H3>
      <Text>
        M0042（2027）、M0057（2042）、M0044（2029）、M0073（2058）は日次が +5,000 超と −3,000 超を行き来する。
        期末だけ見るとプラスでも、途中の谷が深い。M0057 は 8/15 +8,000 の翌日 −4,900、8/20 に再加速 +5,000。
        連続グラフはのこぎり歯で、単日の結果が累積の大半を決める。
      </Text>

      <Callout tone="warning" title="島の位置だけでは説明できない">
        連日削りの M0045（2030）と高値維持の M0054（2039）は番号が近い。
        安定積みの M0067（2052）の隣 M0066（2051）は −6,800。2124島も M0078/80 が強い一方 M0076 は沈んでいる。
        この8日に限れば「島ごと熱い」より「台ごとに当たり日が乗ったか」の差が大きい。
      </Callout>

      <Divider />

      <H2>全50台の期末一覧</H2>
      <Text tone="secondary">
        期末は連続スランプの最終値。ピーク／ボトムはその過程の最大・最小。直近2日は 8/20–21 の日次終値平均（8/21は途中）。
      </Text>
      <Table
        headers={["実台", "台番号", "期末累積", "ピーク", "ボトム", "直近2日", "型"]}
        columnAlign={["left", "right", "right", "right", "right", "right", "left"]}
        rows={ALL_ROWS.map((r) => [r.mid, r.unit, r.final, r.peak, r.trough, r.last2, r.pattern])}
        rowTone={ALL_ROWS.map((r) => r.tone)}
        striped
        stickyHeader
      />

      <Callout tone="neutral" title="この考察の限界">
        連続スランプは各日の差枚を平行移動して繋いだもので、実台の設定や期待値の推定ではない。
        対象は8日・50台、8/21は営業途中。マギアレコード特有の AT 当たり日がサンプルを支配するため、
        翌週に同じ台が同じ型を繰り返す保証はない。遊技判断にするなら、直近2日の向きと「単日依存かどうか」をセットで見る。
      </Callout>
    </Stack>
  );
}

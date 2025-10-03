인포그래픽을 자동으로 생성하는 프레임웍을 설계하려고 합니다. 다음과같은
구성요소를 가지고 있습니다.

## 인포그래픽 템플릿

인포그래픽을 생성해주는 정보를 담고있는 JSON 파일입니다. 인포그래픽 템플릿은
인포그래픽 요소, 수식, 스타일을 포함합니다.

ex) 다음과 같은 형태입니다.

```json
{
  "numElementsRange": [1, 5], // 인포그래픽 요소의 갯수 범위
  "schema": { ... }, // 입력 값의 스키마 참조
  "elements": [ ... ], // 인포그래픽 요소 참조
  "formulas": { ... }, // 수식 참조
  "styles": { ... } // 스타일 참조
}
```

## 인포그래픽 요소

각 항목을 구성하는 SVG 요소입니다. 동적인 속성을 가질 수 있습니다. 동적인 속성의
값은 E4X 또는 JSX와 같이 {key} 형태로 표현됩니다.

ex)

```xml
<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{fill}"/>
```

각 svg 스트링은 인포그래픽 템플릿의 elements 요소에 배열로 포함됩니다.

ex)

```json
"elements": [
  "<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"{height}\" fill=\"{fill}\"/>",
  "<text x=\"{textX}\" y=\"{textY}\" font-size=\"{fontSize}\" fill=\"{textFill}\">{text}</text>"
]
```

## 수식

인포그래픽 요소의 동적인 속성 값을 계산하는 수식입니다. 입력 값의 종류는 다음과
같습니다. index: 인포그래픽 요소의 인덱스 (숫자형, 0부터 시작) value: 인포그래픽
요소의 값 (숫자형) total: 인포그래픽 요소의 갯수 (숫자형) screenWidth:
인포그래픽이 렌더링되는 화면의 너비 (숫자형) screenHeight: 인포그래픽이
렌더링되는 화면의 높이 (숫자형)

ex)

```json
"formulas": {
  "x": "index * (screenWidth / total)",
  "y": "screenHeight / 2",
  "width": "(screenWidth / total) - 10",
  "height": "value * (screenHeight / 100)",
  "fill": "'#'+(Math.floor(Math.random()*16777215).toString(16))",
  "textX": "x + (width / 2)",
  "textY": "y - 10",
  "fontSize": "14",
  "textFill": "'#000'",
  "text": "'Value: ' + value"
}
```

## 스타일

인포그래픽의 전반적인 스타일을 정의합니다. 배경색, 폰트, 여백 등을 포함할 수
있습니다. 이 값은 인포그래픽 요소의 동적 변수로 사용할 수 있습니다.

```json
"styles": {
  "backgroundColor": "#ffffff",
  "fontFamily": "Arial, sans-serif",
  "margin": 10,
  ...
}
```

ex) 다음과 같이 styles의 값을 인포그래픽 요소에서 사용할 수 있습니다.

```xml
<rect width="100%" height="100%" fill="{styles.backgroundColor}"/>
```

## 입력값의 스키마

인포그래픽을 생성할 때 필요한 입력 값의 스키마입니다. JSON Schema 형태로
제공됩니다. 입력 값은 인포그래픽 요소 데이터에 대한 배열로 제공됩니다.

ex)

```json
"schema": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "text": {"type": "string"},
      "description": {"type": "string"},
      "value": {"type": "number"}
    },
    "required": ["text", "value"]
  }
}
```

## 입력 값

인포그래픽을 생성할 때 필요한 입력 값입니다. 인포그래픽 요소 데이터에 대한
배열로 제공됩니다. 각 항목은 인포그래픽 요소의 값(value)을 포함합니다.

ex)

```json
[
  { "text": "A", "value": 90, "description": "Description for A" },
  { "text": "B", "value": 70, "description": "Description for B" },
  { "text": "C", "value": 50, "description": "Description for C" }
]
```

## 전체 예시

종합하면, 각 입력값을 바탕으로 수식을 계산하여 인포그래픽 요소의 동적 속성 값을
결정하고, 이를 통해 최종 SVG를 생성하는 방식입니다.

아래의 전체 JSON 예시는 위의 모든 구성요소를 포함한 인포그래픽 템플릿의
예시입니다.

```json
{
  "numElementsRange": [1, 5],
  "schema": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "text": { "type": "string" },
        "description": { "type": "string" },
        "value": { "type": "number" }
      },
      "required": ["text", "value"]
    }
  },
  "elements": [
    "<rect x=\"{x}\" y=\"{y}\" width=\"{width}\" height=\"{height}\" fill=\"{styles.backgroundColor}\"/>",
    "<circle cx=\"{x}\" cy=\"{y}\" r=\"{width}\" fill=\"{styles.backgroundColor}\"/>"
  ],
  "formulas": {
    "elementIndex": "index % 2",
    "x": "index * (screenWidth / total)",
    "y": "screenHeight / 2",
    "width": "(screenWidth / total) - 10",
    "height": "value * (screenHeight / 100)",
    "fontSize": "14",
    "colorIndex": "index % styles.colors.length",
    "text": "'Value: ' + value"
  },
  "styles": {
    "backgroundColor": "#ff0000ff",
    "fontFamily": "Arial, sans-serif",
    "margin": 10,
    "colors": ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#00ffff"]
  }
}
```

## 생성 과정

1. 인포그래픽 템플릿을 로드합니다.
2. screenWidth, screenHeight 크기의 SVG 캔버스를 생성합니다.
3. 순차적으로 인포그패픽 요소를 formula에 대입합니다. 이때 index 값은 자동으로
   할당됩니다. (sympy 사용)
4. 계산된 값을 인포그래픽 요소의 동적 속성에 대입합니다.
5. 인포그래픽 요소의 속성을 추가하여 SVG 요소를 완성합니다.
6. 모든 인포그래픽 요소를 SVG 캔버스에 추가합니다.
7. 최종 SVG를 출력합니다.

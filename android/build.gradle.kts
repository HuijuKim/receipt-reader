// 루트 빌드 스크립트 — 플러그인 버전만 선언하고 적용은 app 모듈에서 합니다.
//   AGP 8.9 이상이어야 compileSdk 36(Android 16)을 지원합니다.
//   Kotlin 2.0 부터는 Compose 컴파일러가 별도 플러그인으로 분리됐습니다.
plugins {
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("com.google.devtools.ksp") version "2.0.21-1.0.25" apply false  // Room 코드생성
}

// 빌드 산출물 위치.
//   이 프로젝트는 OneDrive 동기화 폴더 안에 있습니다. Gradle 이 build/ 아래에
//   파일을 만들면 OneDrive 가 곧바로 열어 동기화하는데, 그 사이 Gradle 이
//   같은 폴더를 지우려다 "Unable to delete directory" 로 실패합니다.
//   gradle.properties 의 buildOutputDir 로 산출물만 동기화 밖으로 뺍니다.
//   (프로퍼티를 지우면 예전처럼 프로젝트 안의 build/ 를 씁니다)
val buildOutputDir = (findProperty("buildOutputDir") as String?)?.takeIf { it.isNotBlank() }
if (buildOutputDir != null) {
    allprojects {
        layout.buildDirectory.set(
            file("$buildOutputDir/${rootProject.name}/${project.path.replace(':', '_').trim('_')}")
        )
    }
}

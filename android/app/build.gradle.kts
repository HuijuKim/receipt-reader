plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")   // Kotlin 2.0+ 의 Compose 컴파일러
    id("com.google.devtools.ksp")               // Room 코드생성
}

android {
    namespace = "com.example.receiptreader"
    compileSdk = 36                     // 설치된 SDK 플랫폼(android-36.1)에 맞춤

    defaultConfig {
        applicationId = "com.example.receiptreader"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"

        // 서버 주소의 '초기값'입니다. 앱의 [설정] 탭에서 바꾼 값이 우선하며,
        // 그 값은 기기에 저장됩니다 (Settings.kt).
        //   - 에뮬레이터에서 PC의 localhost 는 10.0.2.2
        //   - 외부 망에서 쓸 때는 Cloudflare 터널 주소를 [설정] 탭에 붙여넣습니다
        buildConfigField("String", "SERVER_URL", "\"http://10.0.2.2:8000/\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")

    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // 네트워크 (사진 업로드 + JSON 파싱)
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.11.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // 이미지 미리보기
    implementation("io.coil-kt:coil-compose:2.6.0")

    // 로컬 저장 (인식 결과 보관)
    val roomVersion = "2.6.1"
    implementation("androidx.room:room-runtime:$roomVersion")
    implementation("androidx.room:room-ktx:$roomVersion")
    ksp("androidx.room:room-compiler:$roomVersion")
}

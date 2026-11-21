plugins { id("com.android.application"); id("org.jetbrains.kotlin.plugin.compose") }
val qualifyRelease = providers.gradleProperty("vipiReleaseQualification").map { it.toBooleanStrict() }.getOrElse(false)
val qualifySourceContext = providers.gradleProperty("vipiSourceContextQualification").map { it.toBooleanStrict() }.getOrElse(false)
val qualifyGroups = providers.gradleProperty("vipiGroupsQualification").map { it.toBooleanStrict() }.getOrElse(false)
require(!qualifyGroups || qualifySourceContext) { "Groups qualification requires isolated debug configuration." }
// Public auth configuration and private upload-key inputs are supplied by the release environment.
// Missing production inputs must never produce an apparently distributable blank-auth build.
fun releaseInput(property: String, environment: String) =
    providers.gradleProperty(property).orElse(providers.environmentVariable(environment))
val releaseWorkosClientId = releaseInput("vipiWorkosClientId", "VIPI_WORKOS_CLIENT_ID")
val releaseUploadStore = releaseInput("vipiUploadStoreFile", "VIPI_UPLOAD_STORE_FILE")
val releaseUploadStorePassword = releaseInput("vipiUploadStorePassword", "VIPI_UPLOAD_STORE_PASSWORD")
val releaseUploadKeyAlias = releaseInput("vipiUploadKeyAlias", "VIPI_UPLOAD_KEY_ALIAS")
val releaseUploadKeyPassword = releaseInput("vipiUploadKeyPassword", "VIPI_UPLOAD_KEY_PASSWORD")
val productionClientId = if (qualifyRelease) "" else releaseWorkosClientId.orNull.orEmpty()
val firebaseConfigFile = releaseInput("vipiFirebaseConfigFile", "VIPI_FIREBASE_CONFIG_FILE")
val firebaseConfig: Map<String, String> = if (qualifyRelease || qualifySourceContext || !firebaseConfigFile.isPresent) emptyMap() else {
    val document = groovy.json.JsonSlurper().parse(file(firebaseConfigFile.get())) as Map<*, *>
    val project = document["project_info"] as Map<*, *>
    val client = (document["client"] as List<*>).map { it as Map<*, *> }.single {
        (((it["client_info"] as Map<*, *>)["android_client_info"] as Map<*, *>)["package_name"]) == "co.fallsoft.vipi"
    }
    mapOf("PROJECT_ID" to project["project_id"].toString(), "SENDER_ID" to project["project_number"].toString(),
        "APP_ID" to (client["client_info"] as Map<*, *>)["mobilesdk_app_id"].toString(),
        "API_KEY" to ((client["api_key"] as List<*>).first() as Map<*, *>)["current_key"].toString())
        .also { values -> require(values.values.all { it.matches(Regex("[A-Za-z0-9:_-]+")) }) }
}
require(productionClientId.isEmpty() || productionClientId.matches(Regex("client_[A-Za-z0-9]+"))) {
    "Vipi production WorkOS client ID must be a public client_ identifier."
}
android {
    namespace = "co.fallsoft.vipi"
    compileSdk { version = release(37) { minorApiLevel = 0 } }
    ndkVersion = "29.0.14206865"
    externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt"); version = "3.22.1" } }
    defaultConfig {
        applicationId = "co.fallsoft.vipi"
        minSdk = 29
        targetSdk = 36
        versionCode = 21
        versionName = "1.0.20"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        externalNativeBuild { cmake { arguments += "-DANDROID_STL=c++_static" } }
        buildConfigField("boolean", "GROUPS_QUALIFICATION", "false")
        buildConfigField("boolean", "FIREBASE_CONFIGURED", firebaseConfig.isNotEmpty().toString())
        buildConfigField("boolean", "DEFAULT_FULL_IMMERSION", providers.gradleProperty("vipiFullImmersionReview").map { it.toBooleanStrict() }.getOrElse(false).toString())
        for (key in listOf("PROJECT_ID", "SENDER_ID", "APP_ID", "API_KEY"))
            buildConfigField("String", "FIREBASE_$key", "\"${firebaseConfig[key].orEmpty()}\"")
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17; isCoreLibraryDesugaringEnabled = true }
    buildFeatures { compose = true; buildConfig = true }
    signingConfigs {
        create("productionUpload") {
            releaseUploadStore.orNull?.takeIf { it.isNotBlank() }?.let { storeFile = file(it) }
            storePassword = releaseUploadStorePassword.orNull
            keyAlias = releaseUploadKeyAlias.orNull
            keyPassword = releaseUploadKeyPassword.orNull
        }
    }
    // Opt-in, separately installed qualification of the optimized release path.
    // The local debug certificate is never configured for a normal release.
    buildTypes {
        getByName("debug") {
            buildConfigField("boolean", "GROUPS_QUALIFICATION", qualifyGroups.toString())
            if (qualifySourceContext) applicationIdSuffix = when {
                qualifyGroups -> ".groupsqa"
                providers.gradleProperty("vipiTutorialQualification").map { it.toBooleanStrict() }.getOrElse(false) -> ".tutorialqa"
                else -> ".sourcecontextqa"
            }
            buildConfigField("String", "WORKOS_CLIENT_ID", "\"${productionClientId.ifBlank { "client_01M5S2CDSQ8F7FEX26G3CY9VS1" }}\"")
            providers.gradleProperty("vipiQaAbi").orNull?.let { require(it in setOf("x86_64", "arm64-v8a")); ndk.abiFilters.add(it) }
        }
        getByName("release") {
            // Optional phone-delivery slice; normal release/store builds retain all ABIs.
            providers.gradleProperty("vipiReleaseAbi").orNull?.let {
                require(it == "arm64-v8a") { "Only the reviewed arm64 phone slice is supported." }
                ndk.abiFilters.add(it)
            }
            buildConfigField("String", "WORKOS_CLIENT_ID", "\"$productionClientId\"")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("productionUpload")
            if (qualifyRelease) {
                applicationIdSuffix = ".qualification"
                signingConfig = signingConfigs.getByName("debug")
                providers.gradleProperty("vipiQaAbi").orNull?.let { require(it in setOf("x86_64", "arm64-v8a")); ndk.abiFilters.add(it) }
            }
        }
    }
    sourceSets.getByName("androidTest").assets.srcDir("../../qa/backup")
    packaging {
        // Upstream ships JNI testing binaries and desktop natives alongside the
        // mobile implementation. They are not part of the Android runtime.
        jniLibs.excludes += "**/libsignal_jni_testing.so"
        resources.excludes += setOf("**/*.dll", "**/*.dylib", "**/*.so")
        resources.merges += setOf("META-INF/LICENSE.md", "META-INF/NOTICE.md", "META-INF/CONTRIBUTORS.md")
        resources.merges += setOf("META-INF/LICENSE", "META-INF/NOTICE", "META-INF/DEPENDENCIES")
    }
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
// Translation models are managed by ML Kit. Historical lookup catalogs and
// authored examples must never enter the client package or its runtime path.
val clientResourceOutput = objects.directoryProperty().apply {
    set(layout.buildDirectory.dir("generated/clientResources"))
}
val stageClientResources = tasks.register<Sync>("stageClientResources") {
    // Live pinyin transliteration data, not a message translation catalog.
    from("../../data/readings") { include("chinese-ordinary.json"); into("readings") }
    from(rootProject.file("LICENSE")) { into("licenses/vipi") }
    from(rootProject.file("NOTICE")) { into("licenses/vipi") }
    into(clientResourceOutput)
}
androidComponents.onVariants { variant ->
    variant.sources.assets?.addGeneratedSourceDirectory(stageClientResources) { clientResourceOutput }
}
tasks.named("preBuild") { dependsOn(stageClientResources) }
val verifyProductionRelease = tasks.register("verifyProductionRelease") {
    group = "verification"
    description = "Reject production release builds without explicit auth and upload signing configuration."
    doLast {
        check(!qualifySourceContext) { "Source-context qualification is a debug-only isolated package." }
        check(!qualifyGroups) { "Groups qualification is never a release configuration." }
        if (qualifyRelease) return@doLast
        check(productionClientId.isNotBlank()) {
            "Set VIPI_WORKOS_CLIENT_ID (or vipiWorkosClientId) to the production public WorkOS client ID."
        }
        check(productionClientId != "client_01M5S2CDSQ8F7FEX26G3CY9VS1") {
            "The known staging WorkOS client must not be used for a production release."
        }
        check(!providers.gradleProperty("vipiQaAbi").isPresent) {
            "vipiQaAbi is a qualification-only option; omit it for production release."
        }
        check(firebaseConfig["PROJECT_ID"] == "mambo-vipi-4f569") {
            "Set VIPI_FIREBASE_CONFIG_FILE to Vipi's registered Android Firebase configuration."
        }
        val store = releaseUploadStore.orNull?.takeIf { it.isNotBlank() }?.let { file(it) }
        check(store != null && store.isFile && store.canRead()) {
            "Set VIPI_UPLOAD_STORE_FILE (or vipiUploadStoreFile) to the readable production upload keystore."
        }
        check(listOf(releaseUploadStorePassword, releaseUploadKeyAlias, releaseUploadKeyPassword)
            .all { !it.orNull.isNullOrBlank() }) {
            "Supply the production upload keystore password, key alias and key password through the release environment."
        }
    }
}
tasks.matching { it.name == "preReleaseBuild" }.configureEach { dependsOn(verifyProductionRelease) }
dependencies {
    implementation("com.google.firebase:firebase-messaging:26.0.1")
    implementation("androidx.work:work-runtime-ktx:2.12.0")
    implementation("androidx.lifecycle:lifecycle-process:2.10.0")
    implementation("com.atilika.kuromoji:kuromoji-ipadic:0.9.0")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
    implementation(project(":core"))
    implementation(platform("androidx.compose:compose-bom:2026.11.01"))
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended:1.6.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    implementation("com.google.mlkit:translate:17.0.3")
    implementation("com.google.mlkit:language-id:17.0.6")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.workos:workos-android:0.4.0")
    implementation("androidx.browser:browser:1.9.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    androidTestImplementation(platform("androidx.compose:compose-bom:2026.11.01"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
    implementation("org.signal:libsignal-android:0.105.0")
}

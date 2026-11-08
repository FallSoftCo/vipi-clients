plugins { id("com.android.application") }
val retained = providers.gradleProperty("retainedAssets").get()
android {
 namespace = "co.fallsoft.vipi.opennlpqa"
 compileSdk = 36
 buildToolsVersion = "36.0.0"
 defaultConfig { applicationId = "co.fallsoft.vipi.opennlpqa"; minSdk = 28; targetSdk = 36; versionCode = 1; versionName = "runtime-r01" }
 compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17; isCoreLibraryDesugaringEnabled = true }
 buildTypes {
  getByName("release") { isMinifyEnabled = true; isDebuggable = false; signingConfig = signingConfigs.getByName("debug"); proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro") }
 }
 packaging { resources.excludes += setOf("META-INF/LICENSE", "META-INF/NOTICE", "META-INF/LICENSE.txt", "META-INF/DEPENDENCIES") }
}
dependencies {
 implementation(files("$retained/opennlp-tools-2.5.10.jar", "$retained/slf4j-api-2.0.18.jar"))
 coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}

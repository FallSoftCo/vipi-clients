pluginManagement {
    // Kotlin 2.4 needs newer D8/R8 than AGP 8.13 bundles. Use Google's documented override.
    buildscript {
        repositories { google(); mavenCentral() }
        dependencies { classpath("com.android.tools:r8:9.5.28") }
    }
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google(); mavenCentral()
        maven { url = uri("https://build-artifacts.signal.org/libraries/maven/"); content { includeGroup("org.signal") } }
    }
}
rootProject.name = "Vipi"
include(":app", ":core")

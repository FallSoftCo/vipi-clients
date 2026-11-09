pluginManagement {
 buildscript { repositories { google(); mavenCentral() }; dependencies { classpath("com.android.tools:r8:9.5.28") } }
 repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }
rootProject.name = "VipiContextPackQualification"
include(":app")

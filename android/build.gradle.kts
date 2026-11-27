plugins {
    id("com.android.application") version "9.1.1" apply false
    id("org.jetbrains.kotlin.jvm") version "2.4.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.0" apply false
}

val ktfmt by configurations.creating {
    isCanBeConsumed = false
    isTransitive = false
}

dependencies {
    ktfmt("com.facebook:ktfmt:0.64:with-dependencies@jar")
}

val kotlinSources =
    fileTree(projectDir) {
        include(
            "app/src/**/*.kt",
            "core/src/**/*.kt",
            "*.gradle.kts",
            "app/*.gradle.kts",
            "core/*.gradle.kts",
        )
    }

for (taskName in listOf("formatKotlin", "checkKotlinFormat")) {
    tasks.register<JavaExec>(taskName) {
        val checkOnly = taskName == "checkKotlinFormat"
        group = if (checkOnly) "verification" else "formatting"
        description =
            if (checkOnly) "Check app and core Kotlin formatting."
            else "Format app and core Kotlin."
        classpath = ktfmt
        mainClass.set("com.facebook.ktfmt.cli.Main")
        maxHeapSize = "1400m"
        jvmArgs("-XX:ActiveProcessorCount=3")
        inputs.files(kotlinSources)
        args("--kotlinlang-style", "--do-not-remove-unused-imports")
        if (checkOnly) args("--dry-run", "--set-exit-if-changed")
        args(kotlinSources.files.sortedBy { it.path })
    }
}

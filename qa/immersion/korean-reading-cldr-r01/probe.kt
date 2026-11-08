package co.fallsoft.vipi

import java.util.Base64

/** Base64-framed TSV avoids changing any source whitespace or script. */
fun main(arguments: Array<String>) {
    val decoder = Base64.getDecoder()
    val encoder = Base64.getEncoder()
    fun encode(value: String) = encoder.encodeToString(value.toByteArray(Charsets.UTF_8))
    for (line in generateSequence(::readLine)) {
        val fields = line.split('\t')
        require(fields.size == 2)
        val text = String(decoder.decode(fields[1]), Charsets.UTF_8)
        if (arguments.firstOrNull() == "letters") {
            println(fields[0] + "\t" + encode(KoreanLetterRules.romanize(text)))
            continue
        }
        val start = System.nanoTime()
        val first = KoreanReadingCandidate.resolve(text)
        val firstNs = System.nanoTime() - start
        val warmStart = System.nanoTime()
        val warm = KoreanReadingCandidate.resolve(text)
        val warmNs = System.nanoTime() - warmStart
        check(first == warm)
        val pieces = first.pieces.joinToString(";") {
            listOf(it.startUTF16.toString(), it.endUTF16.toString(), encode(it.source),
                encode(it.rendered), it.kind, it.insertedSeparator.toString()).joinToString(",")
        }
        println(listOf(fields[0], first.reading?.let(::encode) ?: "-", encode(first.inspection),
            first.issues.joinToString(","), firstNs.toString(), warmNs.toString(), pieces).joinToString("\t"))
    }
}

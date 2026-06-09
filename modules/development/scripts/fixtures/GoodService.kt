package com.example.fixtures

import org.slf4j.LoggerFactory

class GoodService(private val repository: AccountRepository) {

    private val log = LoggerFactory.getLogger(GoodService::class.java)

    fun isBlocked(accountId: String): Boolean {
        val account = repository.find(accountId) ?: return false
        log.debug("checked block status for {}", accountId)
        return account.blocked
    }
}

interface AccountRepository {
    fun find(accountId: String): Account?
}

data class Account(val id: String, val blocked: Boolean)
